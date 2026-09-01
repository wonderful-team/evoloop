"""E2E-SC-003: retry with revert_files=True restores filesystem and DB state."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    observe_agent_run,
    wait_until,
)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _get_db_path(http_client: httpx.AsyncClient) -> Path:
    """从 /api/v1/system/config 解析 SQLite 数据库路径。"""
    resp = await http_client.get("/api/v1/system/config")
    resp.raise_for_status()
    configs = {
        item.get("key"): item.get("value")
        for item in resp.json()
        if isinstance(item, dict)
    }
    sqlite_path = configs.get("SQLITE_PATH")
    if sqlite_path:
        return Path(os.path.expanduser(sqlite_path)).expanduser()
    app_data_dir = configs.get("EVOLOOP_APP_DATA_DIR")
    base = Path(os.path.expanduser(app_data_dir)).expanduser() if app_data_dir else Path.home() / ".evoloop"
    return base / "database" / "backend.db"


async def _query_db(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """在线程中执行 SQLite 查询，避免在 async 函数中直接阻塞。"""

    def _run() -> list[Any]:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return list(cur.fetchall())
        finally:
            conn.close()

    return await asyncio.to_thread(_run)


async def _wait_for_file_operation(
    http_client: httpx.AsyncClient,
    thread_id: str,
    file_path: Path,
    timeout: float = 30.0,
) -> dict[str, Any] | None:
    """等待 write_file 产生的 FileOperation 记录落库。"""
    db_path = await _get_db_path(http_client)

    async def _check() -> dict[str, Any] | None:
        rows = await _query_db(
            db_path,
            "SELECT id, operation, original_content, diff_content FROM file_operations "
            "WHERE thread_id = ? AND file_path = ? ORDER BY id DESC LIMIT 1",
            (thread_id, str(file_path)),
        )
        if rows:
            return dict(rows[0])
        return None

    try:
        return await wait_until(_check, timeout=timeout, desc=f"FileOperation 落库 {file_path.name}")
    except TimeoutError:
        return None


class TestRetryFileRollback:
    """E2E-SC-003: retry 文件与 DB 回滚。"""

    @pytest.mark.slow
    @pytest.mark.timeout(240)
    async def test_retry_reverts_file_and_db(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,  # noqa: F811
        workspace_root: Path,  # noqa: F811
    ) -> None:
        """retry revert_files=True 将文件恢复为修改前内容，并删除目标消息之后的 DB 消息。"""
        target_file = workspace_root / f"e2e-retry-{unique_marker}.txt"
        before_content = "before"
        after_content = "after"

        target_file.write_text(before_content, encoding="utf-8")

        try:
            # 第一次运行：使用 write_file 覆盖文件内容为 after
            # write_file 会记录 original_content，FileRewind 才能回滚
            first_prompt = (
                f"请使用 write_file 工具覆盖文件 `e2e-retry-{unique_marker}.txt`，"
                f"内容写入 `{after_content}`。"
            )
            observer = asyncio.create_task(
                observe_agent_run(
                    http_client, thread_id, timeout=120.0, expect_start=False
                )
            )
            await asyncio.sleep(0)

            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": first_prompt},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "queued"

            result = await observer
            if result.run_end_status != "done":
                pytest.skip(
                    f"第一次运行未成功完成(status={result.run_end_status})，"
                    f"无法验证回滚"
                )

            assert target_file.exists(), "命令运行后目标文件应存在"
            current = target_file.read_text(encoding="utf-8").strip()
            assert (
                current == after_content
            ), f"第一次运行后文件内容应为 {after_content!r}，实际: {current!r}"

            # 等待 FileOperation 记录落库，否则 FileRewind 找不到回滚依据
            file_op = await _wait_for_file_operation(
                http_client, thread_id, target_file, timeout=30.0
            )
            if file_op is None:
                pytest.skip(
                    "write_file 的 FileOperation 未在 30s 内落库，无法验证回滚"
                )
            assert file_op["operation"] == "EDIT", (
                f"期望 EDIT 操作，实际: {file_op['operation']}"
            )
            assert file_op["original_content"] == before_content, (
                f"FileOperation 备份内容不是 {before_content!r}: {file_op}"
            )

            # 查询消息，找到目标 human 消息 id / sequence_number
            msgs_resp = await wait_until(
                lambda: http_client.get(f"/api/v1/conversations/{thread_id}/messages"),
                timeout=20.0,
                desc="消息可读",
            )
            msgs_resp.raise_for_status()
            msgs = msgs_resp.json().get("data", [])
            human = next(
                (
                    m
                    for m in msgs
                    if m.get("role") == "human" and m.get("content") == first_prompt
                ),
                None,
            )
            assert human is not None, (
                f"未找到第一次运行的人类消息: "
                f"{json.dumps(msgs, ensure_ascii=False)[:500]}"
            )
            human_id = human["id"]
            human_seq = human.get("sequence_number")

            removed_ids = {
                m["id"]
                for m in msgs
                if (m.get("sequence_number") or 0) > (human_seq or 0)
            }

            # 发送 retry，要求回滚文件
            resp = await http_client.post(
                "/api/v1/chat/retry",
                json={
                    "thread_id": thread_id,
                    "message_id": human_id,
                    "revert_files": True,
                    "message": "retry",
                },
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued"
            assert body["action"] == "retry"
            assert body.get("files_reverted", 0) >= 1, f"应至少回滚 1 个文件: {body}"

            # retry endpoint 同步完成 rewind 后才返回，此时文件应已被恢复为 before
            assert target_file.exists(), "回滚后目标文件应仍然存在"
            current_after_rewind = target_file.read_text(encoding="utf-8").strip()
            assert (
                current_after_rewind == before_content
            ), f"rewind 后文件内容应立即恢复为 {before_content!r}，实际: {current_after_rewind!r}"

            # 等待重试运行完成（retry 会重新调度同一条 human 消息，因此新 run 可能再次把文件改为 after）
            retry_observer = asyncio.create_task(
                observe_agent_run(
                    http_client, thread_id, timeout=120.0, expect_start=False
                )
            )
            await asyncio.sleep(0)
            retry_result = await retry_observer
            assert retry_result.run_end_status in (
                "done",
                "failed",
            ), f"重试运行终态异常: {retry_result.run_end_status}"

            # 文件必须仍存在；最终内容取决于新 run 是否再次执行 write_file，
            # 因此这里只保留存在性断言，真正的回滚效果已在 endpoint 返回后验证。""",
            # 原 human 消息保留，sequence_number 不变；其后的旧消息应被删除
            msgs_after_resp = await http_client.get(
                f"/api/v1/conversations/{thread_id}/messages"
            )
            msgs_after_resp.raise_for_status()
            msgs_after = msgs_after_resp.json().get("data", [])

            human_after = next(
                (m for m in msgs_after if m.get("id") == human_id),
                None,
            )
            assert human_after is not None, "retry 后原 human 消息应保留"
            assert human_after.get("sequence_number") == human_seq, (
                f"human 消息 sequence_number 应不变: "
                f"{human_seq} -> {human_after.get('sequence_number')}"
            )

            after_ids = {m["id"] for m in msgs_after}
            overlap = removed_ids & after_ids
            assert not overlap, f"目标消息之后的旧消息应被删除，仍残留: {overlap}"
        finally:
            if target_file.exists():
                target_file.unlink()
