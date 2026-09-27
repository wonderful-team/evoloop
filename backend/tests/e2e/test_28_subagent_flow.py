"""E2E：并行 subagent 完整链路（decompose → spawn → worker → aggregate）。

真实 HTTP + 真实 LLM + 真实 SQLite 双轨验证（docs/subagent-design.md §4.1/§8.3）：
  1. 发一条要求并行 subagent 的消息；
  2. SSE 流式等待 run done；
  3. 直查 ``subagent_runs`` 表断言记录创建与终态；
  4. 观测指标：subagent 数量 / status 分布 / completed 数量 / 最终回复摘要。

链路依赖真实 LLM（Supervisor 需自主选择 decompose_task），受配额与模型行为
影响：若未触发 subagent 或 LLM 配额耗尽，测试 skip 并附原因，不视为失败。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

SUBAGENT_PROMPT = (
    "请用并行 subagent 的方式完成以下三个互不依赖的独立子任务，然后汇总结果："
    "1) 统计 app/core/ 目录下的 .py 文件数量；"
    "2) 统计 tests/unit/ 目录下的 .py 文件数量；"
    "3) 统计 scripts/ 目录下的 .py 文件数量。"
    "每个子任务独立完成、各自使用命令行工具统计，最后汇总三个数字。"
)

DONE_STATUSES = ("completed", "failed", "cancelled")
PENDING_STATUSES = ("running", "awaiting_human", "awaiting_a2a")


async def _get_db_path(http_client: httpx.AsyncClient) -> Path:
    resp = await http_client.get("/api/v1/system/config", timeout=10.0)
    configs = resp.json() if resp.status_code == 200 else []
    config_map = {c.get("key"): c.get("value") for c in configs}
    app_data_dir = config_map.get("EVOLOOP_APP_DATA_DIR")
    base = (
        Path(os.path.expanduser(app_data_dir)).expanduser()
        if app_data_dir
        else Path.home() / ".evoloop"
    )
    return base / "database" / "backend.db"


async def _query_db(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    def _run() -> list[Any]:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            conn.commit()
            return list(cur.fetchall())
        finally:
            conn.close()

    return await asyncio.to_thread(_run)


async def _send_message(
    http_client: httpx.AsyncClient, tid: str, message: str
) -> httpx.Response:
    return await http_client.post(
        "/api/v1/chat",
        json={"message": message, "thread_id": tid, "project_id": 120},
        timeout=30.0,
    )


async def _wait_subagents_terminal(
    db_path: Path, tid: str, timeout: float = 120.0
) -> list[Any]:
    """轮询 subagent_runs 表，等待全部 subagent 进入终态。

    父会话 SSE 的 session_completed 只代表父流程结束，后台 subagent 是
    异步执行的，需要单独等待其收尾（done_callback 写入终态）。
    """
    deadline = time.monotonic() + timeout
    while True:
        rows = await _query_db(
            db_path,
            "SELECT id, status, instruction, error FROM subagent_runs "
            "WHERE parent_thread_id = ? ORDER BY rowid",
            (tid,),
        )
        if rows and all(r["status"] in DONE_STATUSES for r in rows):
            return rows
        if time.monotonic() > deadline:
            return rows
        await asyncio.sleep(5)


def _event_payload(ev) -> dict[str, Any]:
    try:
        return json.loads(ev.data)
    except Exception:
        return {}


class TestParallelSubagentFlow:
    @pytest.mark.timeout(400)
    async def test_parallel_subagent_records_and_terminal(
        self, http_client: httpx.AsyncClient
    ) -> None:
        tid = f"e2e-subagent-{uuid.uuid4().hex[:12]}"

        resp = await _send_message(http_client, tid, SUBAGENT_PROMPT)
        assert resp.status_code in (200, 202), f"chat 发送失败: {resp.status_code} {resp.text}"

        from tests.e2e.conftest import SSEEmitter, collect_sse_until

        received: list[SSEEmitter] = []

        def _pred(ev: SSEEmitter) -> bool:
            received.append(ev)
            p = _event_payload(ev)
            if ev.event == "status" and p.get("status") == "done":
                return True
            if ev.event in ("run_end", "session_completed"):
                return True
            return False

        async def _noop(_ev):
            return None

        try:
            await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{tid}",
                _pred,
                timeout=300.0,
                desc="run done",
                on_event=_noop,
            )
        except TimeoutError as e:
            logger.warning("SSE 超时: %s", e)
            received = received or []

        # ---- 观测：SSE 事件类型分布 ----
        from collections import Counter

        event_types = Counter(ev.event for ev in received)
        logger.info("[subagent-e2e] SSE 事件分布: %s", dict(event_types))

        # 观测：subagent 生命周期事件是否透传到父会话 SSE（前端面板数据源）
        subagent_events = [
            _event_payload(ev) for ev in received if ev.event == "subagent"
        ]
        logger.info(
            "[subagent-e2e] subagent 生命周期事件 %d 个: %s",
            len(subagent_events),
            [(e.get("subagent_thread_id"), e.get("status")) for e in subagent_events],
        )

        # 配额耗尽直接 skip（外部环境限制，非产品缺陷）
        joined = " ".join(
            _event_payload(ev).get("error") or "" for ev in received
        ).lower()
        if "quota" in joined or "quota_exhausted" in json.dumps(
            [_event_payload(ev) for ev in received], ensure_ascii=False
        ).lower():
            pytest.skip("LLM 配额耗尽，跳过 subagent 真实链路验证")

        # ---- 观测核心：subagent_runs 表 ----
        db_path = await _get_db_path(http_client)
        rows = await _query_db(
            db_path,
            "SELECT id, status, instruction, error FROM subagent_runs "
            "WHERE parent_thread_id = ? ORDER BY rowid",
            (tid,),
        )

        if not rows:
            pytest.skip(
                f"Supervisor 未触发 subagent（SSE 事件: {event_types}）。"
                "可能 LLM 未选择并行分解。"
            )

        # 核心：subagent started 生命周期事件必须透传到父会话 SSE（前端面板数据源）
        started_sub_tids = {
            e.get("subagent_thread_id")
            for e in subagent_events
            if e.get("status") == "started"
        }
        db_sub_tids = {r["id"] for r in rows}
        missing = db_sub_tids - started_sub_tids
        assert not missing, (
            f"SSE 未收到 subagent started 事件: db={sorted(db_sub_tids)}, "
            f"received={sorted(started_sub_tids)}, missing={sorted(missing)}"
        )

        # 等待后台 subagent 全部收尾（父会话 SSE 完成不代表 subagent 完成）
        rows = await _wait_subagents_terminal(db_path, tid)

        statuses = [r["status"] for r in rows]
        logger.info(
            "[subagent-e2e] 创建 %d 个 subagent, status 分布: %s",
            len(rows),
            Counter(statuses),
        )

        # ---- 断言 ----
        assert len(rows) >= 2, f"期望至少 2 个并行 subagent，实际 {len(rows)}"
        assert all(r["instruction"] for r in rows), "instruction 不应为空"
        assert all(
            r["status"] in DONE_STATUSES for r in rows
        ), f"存在未收尾的 subagent: {[r['status'] for r in rows]}"

        completed = sum(1 for s in statuses if s == "completed")
        logger.info("[subagent-e2e] completed=%d/%d", completed, len(rows))

        # 观测：aggregate 结果是否出现在最终 AI 回复中
        final_msgs = await _query_db(
            db_path,
            "SELECT content FROM messages WHERE thread_id = ? AND role = 'ai' "
            "AND content != '' ORDER BY sequence_number DESC LIMIT 3",
            (tid,),
        )
        final_text = " ".join(str(m["content"]) for m in final_msgs)
        logger.info(
            "[subagent-e2e] 最终回复摘要: %s",
            final_text[:200].replace("\n", " "),
        )
        logger.info("[subagent-e2e] aggregate 是否含汇总: %s", bool(final_text))
