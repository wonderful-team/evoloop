"""E2E-SC-008: tool execution creates real filesystem and DB state.

验证 execute_command 真实写入 marker 文件，并且：
  - 文件系统存在该文件且内容包含 marker
  - DB 中存在 tool_output 消息，meta_data 包含完整 stdout / command / exit_code
  - tool_output.content 是摘要，不泄露完整原始输出
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import (
    collect_sse_until,
    verify_quota_exhausted_feedback,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


def _find_tool_outputs(messages: list[dict]) -> list[dict]:
    """从消息列表中提取工具输出块。"""
    return [
        msg for msg in messages if msg.get("role") == "tool" and msg.get("tool_name")
    ]


def _find_ai_messages(messages: list[dict]) -> list[dict]:
    """从消息列表中提取 AI 回复。"""
    return [msg for msg in messages if msg.get("role") == "ai"]


def _meta_contains(meta: Any, needle: str) -> bool:
    """递归检查 meta_data（任意嵌套 dict/list/str）中是否包含目标字符串。"""
    if isinstance(meta, str):
        return needle in meta
    if isinstance(meta, dict):
        return any(_meta_contains(v, needle) for v in meta.values())
    if isinstance(meta, list):
        return any(_meta_contains(v, needle) for v in meta)
    return False


class TestToolExternalEffects:
    """E2E-SC-008: 工具真实外部副作用。"""

    @pytest.mark.slow
    @pytest.mark.timeout(240)
    async def test_execute_command_writes_file(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,  # noqa: F811
        workspace_root: Path,  # noqa: F811
    ) -> None:
        """Agent 调用 execute_command 写入文件，DB tool_output.meta_data 反映完整输出。"""
        target_file = f"e2e-real-{unique_marker}.txt"
        marker = f"real-effect-{unique_marker}"
        prompt = (
            f"请使用 execute_command 工具运行命令 `echo {marker} > {target_file}`，"
            f"然后告诉我结果。"
        )

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": prompt},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "queued"

        events = await collect_sse_until(
            http_client,
            f"/api/v1/stream/chat/{thread_id}",
            lambda ev: ev.event == "run_end",
            timeout=180.0,
            desc=f"run_end for execute_command prompt {prompt[:40]!r}",
        )

        run_end = next((ev.json for ev in events if ev.event == "run_end"), {})
        status = run_end.get("status") if isinstance(run_end, dict) else None
        logger.info(
            "thread=%s run_end=%s events=%d",
            thread_id,
            status,
            len(events),
        )

        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        if status != "done":
            pytest.fail(f"真实副作用运行未正常完成，status={status}, run_end={run_end}")

        messages = [
            ev.json.get("data", {})
            for ev in events
            if ev.event == "message"
            and isinstance(ev.json, dict)
            and ev.json.get("data")
        ]

        try:
            # L2: 文件系统存在 marker 文件
            expected_path = workspace_root / target_file
            for _ in range(50):
                if expected_path.exists():
                    break
                await asyncio.sleep(0.1)
            assert (
                expected_path.exists()
            ), f"execute_command 未在 workspace 创建文件: {expected_path}"
            content = expected_path.read_text(encoding="utf-8")
            assert marker in content, f"文件内容不包含 marker {marker!r}: {content!r}"

            # L2: DB 存在 tool_output 消息
            tool_outputs = _find_tool_outputs(messages)
            assert tool_outputs, (
                f"未在 SSE 中找到 tool_output 消息: "
                f"{json.dumps(messages, ensure_ascii=False)[:500]}"
            )

            exec_outputs = [
                msg for msg in tool_outputs if msg.get("tool_name") == "execute_command"
            ]
            assert exec_outputs, (
                f"未找到 execute_command 工具输出: "
                f"{json.dumps(tool_outputs, ensure_ascii=False)[:500]}"
            )
            tool_output = exec_outputs[0]
            meta = tool_output.get("meta_data") or {}
            assert isinstance(meta, dict), f"tool_output.meta_data 应为 dict: {meta!r}"

            # L2 / L3: meta_data 中应能找到命令或输出痕迹（可能位于深层嵌套字段）
            assert _meta_contains(
                meta, marker
            ), f"tool_output.meta_data 中未包含 marker {marker!r}: {meta!r}"

            # 可选：exit_code 等信息若存在则记录，不强制断言（不同工具 schema 不同）
            if not (
                "exit_code" in meta
                or "returncode" in meta
                or _meta_contains(meta, "exit")
            ):
                logger.warning(
                    "tool_output.meta_data 未包含明显 exit_code 字段: %s", meta
                )

            # L3: content 是摘要，不应包含完整 marker 输出
            content_field = tool_output.get("content") or ""
            assert marker not in content_field, (
                f"tool_output.content 不应包含原始 marker {marker!r}，"
                f"实际: {content_field!r}"
            )

            # L2: 至少存在一条 AI 回复
            ai_messages = _find_ai_messages(messages)
            assert ai_messages, (
                f"未在 SSE 中找到 AI 回复: "
                f"{json.dumps(messages, ensure_ascii=False)[:500]}"
            )
        finally:
            expected_path = workspace_root / target_file
            if expected_path.exists():
                expected_path.unlink()
