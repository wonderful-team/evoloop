"""E2E：HITL cancel 链路（`/hitl/cancel`）。

覆盖（真实 HTTP + 真实 SQLite 双轨）：
  1. 存在 pending HITL 请求时，`/hitl/cancel` 返回 cancelled 且关闭 DB 双轨：
     - human_requests 表：pending → cancelled
     - agent_activities 表：human_request_json 被清理（activity 状态复位）
  2. 无 pending 请求时，`/hitl/cancel` 幂等返回 cancelled，不抛错。
  3. messages 表 hitl_request 消息（若存在）同步置为 cancelled。

与单元测试（tests/unit/core/test_hitl_cancel.py）互补：这里验证真实 HTTP
端点 + 真实 DB 持久化副作用，不依赖 LLM（通过 DB 直插构造 pending 状态，
可控且快速）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real, pytest.mark.slow]


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


async def _seed_pending_hitl(db_path: Path, tid: str) -> dict[str, str]:
    """直接向 DB 插入双轨 pending 态：human_requests + messages(hitl_request) + activity。

    真实流程（push_hitl_notification）会同时写 human_requests 表与 messages 表
    （category=hitl_request, status=waiting_human），get_pending_request 从
    messages 表检测——因此必须双轨都插入，cancel 端点才能命中。
    """
    request_id = str(uuid.uuid4())
    tool_call_id = f"call_hitl_{uuid.uuid4().hex[:8]}"
    now = "2026-01-01 00:00:00"
    msg_id = str(uuid.uuid4())

    # A 轨：human_requests
    await _query_db(
        db_path,
        "INSERT OR REPLACE INTO human_requests "
        "(id, thread_id, type, description, status, result, created_at, updated_at) "
        "VALUES (?, ?, 'approval', ?, 'pending', NULL, ?, ?)",
        (request_id, tid, "批准访问测试路径", now, now),
    )

    # B 轨：messages hitl_request（get_pending_request 的检测来源）
    meta = json.dumps(
        {
            "original_tool": {"name": "list_dir", "args": {"path": "/tmp/x"}},
            "hitl_request_id": request_id,
            "authorization": {"resource_path": "/tmp/x", "action": "read"},
        }
    )
    content = json.dumps(
        {
            "id": request_id,
            "type": "approval",
            "prompt": "批准访问测试路径",
            "default_value": "REJECTED",
        }
    )
    await _query_db(
        db_path,
        "INSERT OR REPLACE INTO messages "
        "(id, thread_id, member_id, project_id, role, content, meta_data, "
        " created_at, sequence_number, action_type, category, content_type, "
        " is_visible, status, tool_call_id, tool_name, sync_status, is_remembered) "
        "VALUES (?, ?, 0, NULL, 'system', ?, ?, ?, 1, 'human_request', "
        " 'hitl_request', 'json', 1, 'waiting_human', ?, 'request_approval', "
        " 'pending', 0)",
        (msg_id, tid, content, meta, now, tool_call_id),
    )

    await _query_db(
        db_path,
        "INSERT OR REPLACE INTO agent_activities "
        "(thread_id, status, run_id, main_goal, artifacts_json, "
        " agent_state_json, active_memories_json, human_request_json, "
        " final_outcome, macro_creation_eligible, updated_at) "
        "VALUES (?, 'interrupted', NULL, '', '[]', '{}', '[]', ?, '', 0, ?)",
        (
            tid,
            json.dumps(
                {
                    "id": request_id,
                    "type": "approval",
                    "prompt": "批准访问测试路径",
                    "default_value": "REJECTED",
                }
            ),
            now,
        ),
    )
    return {"request_id": request_id, "tool_call_id": tool_call_id}


async def _cancel_via_http(
    http_client: httpx.AsyncClient, tid: str
) -> httpx.Response:
    return await http_client.post(
        "/api/v1/hitl/cancel",
        json={"thread_id": tid, "reason": "e2e-hitl-cancel"},
        timeout=15.0,
    )


class TestHitlCancelEndpoint:
    @pytest.mark.timeout(60)
    async def test_cancel_closes_db_tracks_and_clears_activity(
        self, http_client: httpx.AsyncClient
    ) -> None:
        tid = f"e2e-hitl-{uuid.uuid4().hex[:12]}"
        db_path = await _get_db_path(http_client)
        seeded = await _seed_pending_hitl(db_path, tid)

        resp = await _cancel_via_http(http_client, tid)
        assert resp.status_code == 200, f"cancel 失败: {resp.status_code} {resp.text}"
        body = resp.json()
        assert body.get("status") == "cancelled", body
        assert body.get("thread_id") == tid

        # A 轨：human_requests 置为 cancelled
        rows = await _query_db(
            db_path,
            "SELECT status FROM human_requests WHERE id = ?",
            (seeded["request_id"],),
        )
        assert rows and rows[0]["status"] == "cancelled", rows

        # B 轨：messages hitl_request 置为 cancelled（finalize_request 双轨原子）
        msgs = await _query_db(
            db_path,
            "SELECT status FROM messages WHERE thread_id = ? AND category = 'hitl_request'",
            (tid,),
        )
        assert msgs and all(m["status"] == "cancelled" for m in msgs), msgs

        # activity：human_request_json 被清理
        acts = await _query_db(
            db_path,
            "SELECT status, human_request_json FROM agent_activities WHERE thread_id = ?",
            (tid,),
        )
        if acts:  # clear_human_request 依赖 AgentActivity 存在
            assert acts[0]["human_request_json"] is None, acts

    @pytest.mark.timeout(60)
    async def test_cancel_without_pending_is_idempotent(
        self, http_client: httpx.AsyncClient
    ) -> None:
        tid = f"e2e-hitl-none-{uuid.uuid4().hex[:12]}"

        resp = await _cancel_via_http(http_client, tid)
        assert resp.status_code == 200, f"cancel 失败: {resp.status_code} {resp.text}"
        body = resp.json()
        assert body.get("status") == "cancelled", body
        assert body.get("request_id") is None
