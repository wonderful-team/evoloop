"""HITL resume persistence integration tests (real SQLite).

Verifies the fix for "HITL 选项未被 Agent 消费"（HITL option not consumed by Agent）:

1. ``update_tool_result_by_tool_call_id`` only updates ``role='tool'`` messages —
   it must NOT overwrite the ``hitl_request`` system message that shares the
   same ``tool_call_id`` (otherwise the HITL payload JSON is corrupted).
2. The resolved tool result is written into the original tool message rather
   than appending a second tool message (which caused a same-tool_call
   double-result mismatch where the LLM rebuilt context from the empty one).
"""

from __future__ import annotations

import json

import pytest

from app.core.engine.message.repository import MessageRepository
from app.models import Message


@pytest.fixture
def repo_scope(test_session_scope, monkeypatch):
    """Point repository's session_scope at the test SQLite DB."""
    import app.core.engine.message.repository as repo_mod

    monkeypatch.setattr(repo_mod, "session_scope", test_session_scope)
    return test_session_scope


async def _seed_hitl_messages(test_session_scope, thread_id="t-hitl"):
    """Seed a tool_output message + a hitl_request system message sharing one
    tool_call_id (exactly the shape produced by ask_human HITL)."""
    async with test_session_scope() as db:
        db.add(
            Message(
                id="msg-tool",
                thread_id=thread_id,
                role="tool",
                content="",
                tool_call_id="call-ask",
                tool_name="ask_human",
                category="tool_output",
                project_id=120,
                member_id=1,
                sequence_number=1,
                status="completed",
            )
        )
        db.add(
            Message(
                id="msg-hitlreq",
                thread_id=thread_id,
                role="system",
                content=json.dumps({"id": "req-1", "type": "choice", "prompt": "p"}),
                tool_call_id="call-ask",
                tool_name="ask_human",
                category="hitl_request",
                project_id=120,
                member_id=0,
                sequence_number=2,
                status="waiting_human",
            )
        )


class TestUpdateToolResultIsolation:
    @pytest.mark.asyncio
    async def test_updates_only_tool_message_not_hitl_request(
        self, repo_scope, test_session_scope
    ):
        """resume 写回结果时只更新 role='tool' 消息，不得覆盖同 tool_call_id 的
        hitl_request（system）载荷。"""
        await _seed_hitl_messages(test_session_scope)

        repo = MessageRepository("t-hitl", project_id=120, member_id=1)
        ok = await repo.update_tool_result_by_tool_call_id(
            "call-ask", "某个外部第三方电商平台"
        )

        assert ok is True
        async with test_session_scope() as db:
            tool = await db.get(Message, "msg-tool")
            hitl = await db.get(Message, "msg-hitlreq")
            # tool 结果已更新为最终结果（Agent 可见）
            assert tool.content == "某个外部第三方电商平台"
            # hitl_request 的 JSON 载荷不得被改写
            assert hitl.content.startswith('{"id"')
            assert json.loads(hitl.content)["id"] == "req-1"
            assert json.loads(hitl.content)["type"] == "choice"

    @pytest.mark.asyncio
    async def test_no_message_returns_false(self, repo_scope, test_session_scope):
        """无匹配 tool 消息 → 返回 False 且不抛异常。"""
        repo = MessageRepository("t-hitl-none", project_id=120, member_id=1)
        assert await repo.update_tool_result_by_tool_call_id("call-ask", "x") is False
