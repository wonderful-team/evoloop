"""E2E：HITL 审批链路固化（`/chat/resume` 批准/拒绝全链路）。

与 test_19（cancel 链路）互补，覆盖终态 v2 的同步链路（真实 HTTP + 真实 SQLite）：

批准流（skip_grant 元数据 → 不落盘 grant，重执行走 DB 双轨认领放行）：
  1. DB 直插双轨 pending（human_requests + messages hitl_request）；
  2. `POST /chat/resume {user_input: "yes"}` → 200 resuming；
  3. 断言：human_requests completed+APPROVED、messages 全部离开 waiting_human；
  4. 被门控工具真实重执行（marker 文件落地 = 授权后重执行生效）。

拒绝流（带 resource_path 列）：
  1. `POST /chat/resume {user_input:"no"}`；
  2. human_requests：result=REJECTED、expires_at 落盘（拒绝判死台账）；
  3. 不重执行（marker 不存在）；
  4. messages 双轨关闭。

不依赖 LLM：pending 态由 DB 直插构造（与 test_19 同范式）。resume 端点会在
同步段完成双轨定局与工具重执行，随后才调度后台 agent 恢复（本测试的断言
不等待后台任务）。
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

MARKER_DIR = Path("/tmp")


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


async def _query_db(
    db_path: Path, sql: str, params: tuple[Any, ...] = ()
) -> list[Any]:
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


async def _seed_pending_hitl(
    db_path: Path,
    tid: str,
    *,
    request_id: str,
    tool_call_id: str,
    tool_name: str,
    tool_args: dict,
    command: str,
    with_resource_path: bool,
) -> None:
    """直插双轨 pending：human_requests（含结构化锚点列）+ messages(hitl_request)。"""
    now = "2026-01-01 00:00:00"
    msg_id = str(uuid.uuid4())
    # 序号协议：真实写入统一走 SequenceService（thread_sequences 原子 upsert）。
    # 直插种子消息必须同步推进该计数器（seq=S → next_seq=S+1），否则 resume
    # 端点分配出的 seq 与种子行冲突（UNIQUE thread_id+sequence_number）。
    seq = 100
    next_seq = seq + 1

    await _query_db(
        db_path,
        "INSERT OR REPLACE INTO human_requests "
        "(id, thread_id, type, description, status, result, created_at, updated_at, "
        " resource_path, resource_action) "
        "VALUES (?, ?, 'approval', ?, 'pending', NULL, ?, ?, ?, 'read')",
        (
            request_id,
            tid,
            command,
            now,
            now,
            tool_args.get("path", "/tmp") if with_resource_path else None,
        ),
    )

    meta = json.dumps(
        {
            "original_tool": {"name": tool_name, "args": tool_args},
            "hitl_request_id": request_id,
            "authorization": {"resource_path": "/tmp", "action": "read"},
        }
    )
    content = json.dumps(
        {
            "id": request_id,
            "type": "approval",
            "prompt": command,
            "default_value": "REJECTED",
        }
    )
    await _query_db(
        db_path,
        "INSERT OR REPLACE INTO messages "
        "(id, thread_id, member_id, project_id, role, content, meta_data, "
        " created_at, sequence_number, action_type, category, content_type, "
        " is_visible, status, tool_call_id, tool_name, sync_status, is_remembered) "
        "VALUES (?, ?, 0, NULL, 'system', ?, ?, ?, ?, 'human_request', "
        " 'hitl_request', 'json', 1, 'waiting_human', ?, ?, "
        " 'pending', 0)",
        (msg_id, tid, content, meta, now, seq, tool_call_id, tool_name),
    )
    await _query_db(
        db_path,
        "INSERT INTO thread_sequences (thread_id, next_seq) VALUES (?, ?) "
        "ON CONFLICT (thread_id) DO UPDATE SET next_seq = excluded.next_seq",
        (tid, next_seq),
    )


async def _resume_via_http(
    http_client: httpx.AsyncClient, tid: str, user_input: str
) -> httpx.Response:
    return await http_client.post(
        "/api/v1/chat/resume",
        json={"thread_id": tid, "user_input": user_input},
        timeout=30.0,
    )


class TestHitlResumeApproveChain:
    @pytest.mark.timeout(90)
    async def test_approve_closes_dual_track_and_reexecutes_tool(
        self, http_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        tid = f"e2e-hitl-appr-{uuid.uuid4().hex[:12]}"
        marker = tmp_path / "approve.marker"
        command = f"echo e2e-ok > {marker}"
        db_path = await _get_db_path(http_client)
        await _seed_pending_hitl(
            db_path,
            tid,
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
            tool_name="bash",
            tool_args={"command": command},
            command=command,
            with_resource_path=False,
        )

        resp = await _resume_via_http(http_client, tid, "yes")
        assert resp.status_code == 200, f"resume 失败: {resp.status_code} {resp.text}"
        assert resp.json().get("status") == "resuming"

        # 双轨定局：human_requests → completed + APPROVED
        rows = await _query_db(
            db_path,
            "SELECT status, result FROM human_requests WHERE thread_id = ?",
            (tid,),
        )
        assert rows, rows
        assert all(
            r["status"] == "completed" and r["result"] == "APPROVED" for r in rows
        ), rows

        # messages 双轨离开 waiting_human
        msgs = await _query_db(
            db_path,
            "SELECT status FROM messages WHERE thread_id = ? AND category = 'hitl_request'",
            (tid,),
        )
        assert msgs and all(m["status"] == "completed" for m in msgs), msgs

        # 工具被真实重执行：marker 落地（放行认领链路的端到端证据）
        deadline_resp = await _query_db(
            db_path, "SELECT 1 FROM human_requests WHERE thread_id = ?", (tid,)
        )
        assert deadline_resp, deadline_resp
        for _ in range(20):
            if marker.exists():
                break
            await asyncio.sleep(0.3)
        assert marker.exists(), "授权工具未被重执行（marker 缺失）"
        assert marker.read_text().strip() == "e2e-ok"


class TestHitlResumeRejectChain:
    @pytest.mark.timeout(90)
    async def test_reject_marks_dead_with_ttl_and_skips_reexecution(
        self, http_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        tid = f"e2e-hitl-rjct-{uuid.uuid4().hex[:12]}"
        marker = tmp_path / "reject.marker"
        command = f"echo e2e-ok > {marker}"
        db_path = await _get_db_path(http_client)
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        await _seed_pending_hitl(
            db_path,
            tid,
            request_id=request_id,
            tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
            tool_name="bash",
            tool_args={"command": command},
            command=command,
            with_resource_path=True,
        )

        resp = await _resume_via_http(http_client, tid, "no")
        assert resp.status_code == 200, f"resume 失败: {resp.status_code} {resp.text}"

        # 拒绝判死台账：result=REJECTED + expires_at 落盘（防 ping-pong 数据源）
        rows = await _query_db(
            db_path,
            "SELECT status, result, expires_at, resource_path FROM human_requests "
            "WHERE thread_id = ?",
            (tid,),
        )
        assert rows, rows
        for r in rows:
            assert r["status"] == "completed", r
            assert r["result"] == "REJECTED", r
            assert r["expires_at"] is not None, f"判死 TTL 未落盘: {r}"
            assert r["resource_path"], r

        # messages 双轨关闭
        msgs = await _query_db(
            db_path,
            "SELECT status FROM messages WHERE thread_id = ? AND category = 'hitl_request'",
            (tid,),
        )
        assert msgs and all(m["status"] == "completed" for m in msgs), msgs

        # 拒绝 → 不重执行
        await asyncio.sleep(1.0)
        assert not marker.exists(), "拒绝后工具不应被执行"

        # 同线程同资源再访问 → has_thread_resource_rejection 判死数据已可用
        # （列匹配：同 resource_path 的台账行 result=REJECTED）
        rej = await _query_db(
            db_path,
            "SELECT id FROM human_requests WHERE thread_id = ? AND result = 'REJECTED' "
            "AND resource_path IS NOT NULL AND expires_at IS NOT NULL",
            (tid,),
        )
        assert rej, rej
