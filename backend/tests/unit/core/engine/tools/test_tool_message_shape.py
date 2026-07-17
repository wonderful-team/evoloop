"""Regression tests: tool result messages must be native BaseMessage objects.

Production crash 2026-07-14: commit 49496a26 migrated ContextTrimmer to
native BaseMessage objects, but AgentToolExecutor._create_tool_message still
returned raw dicts. Any agent run that executed a tool crashed on the next
react-loop turn with ``AttributeError: 'dict' object has no attribute 'role'``
inside ContextTrimmer.trim's prune stage.
"""

from app.core.engine.context_trimmer import ContextTrimmer
from app.core.engine.message.native_classes import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor


def _make_executor() -> AgentToolExecutor:
    return AgentToolExecutor(tool_map={}, state=AgentState(), config={})


class TestToolMessageShape:
    def test_create_tool_message_returns_native(self):
        executor = _make_executor()
        msg = executor._create_tool_message(
            content="ok", tool_id="call_1", tool_name="demo", run_id="run_1"
        )
        assert isinstance(msg, ToolMessage)
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_1"
        assert msg.name == "demo"
        assert msg.id
        assert msg.additional_kwargs == {"run_id": "run_1"}

    def test_tool_result_survives_trimmer(self):
        """Exact repro of the production crash: trim over a loop history whose
        tail is a tool result message (second react-loop turn)."""
        executor = _make_executor()
        tool_msg = executor._create_tool_message(
            content="ok", tool_id="call_1", tool_name="demo", run_id=None
        )
        messages = [
            HumanMessage(content="do something"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "demo", "args": {}}],
            ),
            tool_msg,
        ]
        trimmer = ContextTrimmer()
        result = trimmer.trim(
            messages=messages,
            model="gpt-4o",
            node_source="worker",
            stages={"window"},
        )
        assert all(isinstance(m, BaseMessage) for m in result.messages)
        assert result.messages[-1].tool_call_id == "call_1"
