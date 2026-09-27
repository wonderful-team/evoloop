"""AgentToolExecutor contract tests — InvalidArguments feedback + ctx.messages injection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pydantic

from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor


def _tool(name: str = "bash"):
    return SimpleNamespace(name=name, metadata={}, ainvoke=AsyncMock())


async def _trigger(_event, _ctx, **_kwargs):
    return SimpleNamespace(block=False, modified_context=None)


def _executor(tool, state=None):
    return AgentToolExecutor(
        tool_map={tool.name: tool},
        state=state or AgentState(messages=[]),
        config={"configurable": {"thread_id": "t"}, "metadata": {}},
    )


async def test_invalid_arguments_returns_rewrite_feedback():
    tool = _tool()
    tool.ainvoke.side_effect = pydantic.ValidationError.from_exception_data(
        "bash", [{"type": "missing", "loc": ("command",), "msg": "Field required", "input": {}}]
    )
    with patch("app.core.engine.tools.executor.hook_system.trigger", _trigger):
        ex = _executor(tool)
        result = await ex.execute_tool("bash", {"cmd": 1}, "c1", [])

    content = result.message.content
    assert content.startswith("The bash tool was called with invalid arguments")
    assert "rewrite the input" in content


async def test_generic_error_keeps_old_format():
    tool = _tool()
    tool.ainvoke.side_effect = RuntimeError("boom")
    with patch("app.core.engine.tools.executor.hook_system.trigger", _trigger):
        ex = _executor(tool)
        result = await ex.execute_tool("bash", {}, "c1", [])

    assert result.message.content.startswith("Error executing bash: boom")


async def test_ctx_messages_injected_into_config():
    tool = _tool()
    captured = {}

    async def _ainvoke(_args, config=None):
        captured["config"] = config
        return "ok"

    tool.ainvoke.side_effect = _ainvoke
    state = AgentState(messages=[HumanMessage(content="hi")])
    with patch("app.core.engine.tools.executor.hook_system.trigger", _trigger):
        ex = _executor(tool, state=state)
        await ex.execute_tool("bash", {"command": "ls"}, "c1", [])

    assert captured["config"]["configurable"]["_messages"] == state.messages
