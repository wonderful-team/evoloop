"""HITL choice 选项 → 用户选择落为 human 消息（真实 e2e）。

链路：Agent 调用 ``ask_human`` 发起 choice 选项（如"从哪选热门商品"）→
SSE 收到 ``human_request``（type=choice）→ 自动提交第一个选项 → resume 后：

1. 会话中新增一条 ``human`` 消息，内容是用户选择的选项文本（前端可见）。
2. 原 ask_human ``tool`` 消息被更新为选项结果（而非新增第二条 tool 消息，
   避免同 tool_call 双 tool 结果导致 Agent 重建上下文取到空的旧消息）。
3. ``hitl_request``（system）消息的 JSON 载荷不被改写。
4. 落库消息的 ``project_id`` 正确（非 0）。

与 test_real_hitl_approval.py（授权门控 APPROVED 场景）互补：这里验证
ask_human choice 选项被用户消费、且以 human 消息形态出现在会话里。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import SSEEmitter, collect_sse_until

pytestmark = [pytest.mark.e2e, pytest.mark.real]


@dataclass
class ChoiceState:
    hitl_seen: bool = False
    resumed: bool = False
    chosen: str = ""
    thread_id: str = ""


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


async def _make_choice_handler(
    http_client: httpx.AsyncClient, state: ChoiceState
) -> Any:
    """SSE 副作用回调：收到 choice 型 human_request 时提交第一个选项。"""

    async def _on_event(ev: SSEEmitter) -> None:
        if ev.event != "human_request":
            return
        data = ev.json or {}
        request_type = data.get("request_type") or data.get("type")
        if str(request_type) != "choice":
            return
        options = data.get("options") or []
        if not options:
            return
        state.hitl_seen = True
        state.chosen = str(options[0])
        resp = await http_client.post(
            "/api/v1/chat/resume",
            json={"thread_id": state.thread_id, "user_input": state.chosen},
            timeout=15.0,
        )
        if resp.status_code == 200:
            state.resumed = True

    return _on_event


def _extract_choice_options(messages: list[dict[str, Any]]) -> list[str]:
    """从 AI 消息的 ask_human 工具调用里提取 options（供 SSE 提交用）。"""
    options: list[str] = []
    for msg in messages:
        if msg.get("role") != "ai":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            if tc.get("name") != "ask_human":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, dict):
                opts = args.get("options") or []
                options.extend(str(o) for o in opts)
    return options


class TestHITLChoiceUserMessage:
    @pytest.mark.timeout(240)
    async def test_choice_selection_persists_as_human_message(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """choice 选项提交后：落为 human 消息、更新 tool 结果、project_id 正确。"""
        state = ChoiceState(thread_id=thread_id)

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    "先不要执行任何操作。请先调用 ask_human 工具，用 options 给出"
                    "三个选项（选项A、选项B、选项C），让我从中选择，等我回答后再继续。"
                ),
                "project_id": 120,
            },
        )
        assert resp.status_code == 200, resp.text

        on_event = await _make_choice_handler(http_client, state)
        try:
            await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                desc="choice 提交后 run_end",
                on_event=on_event,
            )
        except TimeoutError as exc:
            pytest.fail(f"choice 提交后未在窗口内收到 run_end: {exc}")

        # 核心断言 1：HITL choice 被真正触发并提交。
        assert (
            state.hitl_seen
        ), "未收到 choice 型 human_request（LLM 未调用 ask_human 带 options）"
        assert state.resumed, "choice 选项已触发但 resume 未成功提交"
        assert state.chosen, "未从 human_request 解析出可提交的选项"

        # 核心断言 2：DB 里应出现一条 human 消息（用户选择），且 project_id 正确。
        db_path = await _get_db_path(http_client)
        humans = await _query_db(
            db_path,
            "SELECT content, project_id, role FROM messages "
            "WHERE thread_id = ? AND role = 'human' ORDER BY sequence_number DESC",
            (thread_id,),
        )
        # 初始用户指令是一条 human 消息，choice 选择是第二条 → 至少 2 条
        assert len(humans) >= 2, f"未落成 human 消息: {humans}"
        assert state.chosen in {
            h["content"] for h in humans
        }, f"用户选择未作为 human 消息落库: chosen={state.chosen!r} humans={humans}"
        for h in humans:
            if h["content"] == state.chosen:
                assert h["project_id"] == 120, f"choice human 消息 project_id 丢失: {h}"

        # 核心断言 3：原 ask_human tool 消息被更新为选项结果（非空），
        # 且 hitl_request（system）载荷未被改写。
        tool_rows = await _query_db(
            db_path,
            "SELECT content FROM messages WHERE thread_id = ? AND role = 'tool' "
            "AND tool_name = 'ask_human'",
            (thread_id,),
        )
        assert tool_rows, "未找到 ask_human 的 tool 消息"
        assert any(
            r["content"] and state.chosen in r["content"] for r in tool_rows
        ), f"ask_human tool 结果未被更新为选项: {tool_rows}"

        hitl_rows = await _query_db(
            db_path,
            "SELECT content FROM messages WHERE thread_id = ? AND category = 'hitl_request'",
            (thread_id,),
        )
        if hitl_rows:
            parsed = json.loads(hitl_rows[0]["content"])
            assert (
                isinstance(parsed, dict) and parsed.get("type") == "choice"
            ), f"hitl_request 载荷被改写: {hitl_rows[0]['content'][:200]}"
