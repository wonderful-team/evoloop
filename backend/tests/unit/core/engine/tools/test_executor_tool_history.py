"""Contract tests for the discovery-tool repeat-warning removal.

The hard-coded mechanism (_DISCOVERY_TOOLS / _collect_discovery_queries /
_build_repeat_warning) was deleted from AgentToolExecutor. These tests lock
the intended contract that survives the removal:

1. local_tool_history still records every tool call (signature string) so the
   inference loop can surface it to the model (soft, model-visible history).
2. Tool output content is NOT prefixed with any hard-coded "SYSTEM WARNING".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.hooks import hook_system
from app.core.engine.hooks.schemas import HookResult
from app.core.engine.state.base import AgentState
from app.core.engine.tools.executor import AgentToolExecutor

_CONFIG = {
    "configurable": {
        "thread_id": "t-history",
        "member_id": 1,
        "project_id": 9,
        "run_id": "r-1",
    }
}


def _fake_tool(name: str = "list_macros"):
    tool = type("FakeTool", (), {})()
    tool.name = name
    tool.metadata = {}
    return tool


async def _run_execute_tool(
    tool_name: str = "list_macros",
    tool_args: dict | None = None,
    history: list | None = None,
    hook_result: HookResult | None = None,
):
    executor = AgentToolExecutor(
        tool_map={"list_macros": _fake_tool(), "search_native_tools": _fake_tool("search_native_tools")},
        state=AgentState(),
        config=_CONFIG,
    )
    executor._tool_executor = AsyncMock()
    executor._tool_executor.execute = AsyncMock(return_value="result output")
    history = history if history is not None else []

    with (
        patch.object(hook_system, "trigger", AsyncMock(return_value=hook_result or HookResult(success=True))),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
    ):
        return await executor.execute_tool(
            tool_name=tool_name,
            tool_args=tool_args or {"query": "x"},
            tool_id="call-1",
            local_tool_history=history,
        ), history


@pytest.mark.asyncio
async def test_history_records_tool_signature():
    _, history = await _run_execute_tool()
    assert history == ['list_macros:{"query": "x"}']


@pytest.mark.asyncio
async def test_history_records_second_call_with_new_query():
    _, history = await _run_execute_tool(
        tool_name="list_macros",
        tool_args={"query": "first"},
    )
    _, history = await _run_execute_tool(
        tool_name="list_macros",
        tool_args={"query": "second"},
        history=history,
    )
    assert history == [
        'list_macros:{"query": "first"}',
        'list_macros:{"query": "second"}',
    ]


@pytest.mark.asyncio
async def test_result_has_no_hardcoded_repeat_warning_even_after_many_calls():
    history = ['list_macros:{"query": "x"}'] * 10
    result, _ = await _run_execute_tool(
        tool_args={"query": "x"},
        history=history,
    )
    assert "SYSTEM WARNING" not in result.message.content
    assert "result output" in result.message.content


@pytest.mark.asyncio
async def test_result_has_no_repeat_warning_on_error_path():
    executor = AgentToolExecutor(
        tool_map={"list_macros": _fake_tool()},
        state=AgentState(),
        config=_CONFIG,
    )
    executor._tool_executor = AsyncMock()
    executor._tool_executor.execute = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch.object(hook_system, "trigger", AsyncMock(return_value=HookResult(success=True))),
        patch("app.core.engine.callbacks.bridge._get_callbacks", return_value=[]),
    ):
        result = await executor.execute_tool(
            tool_name="list_macros",
            tool_args={"query": "x"},
            tool_id="call-1",
            local_tool_history=['list_macros:{"query": "x"}'] * 10,
        )
    assert "SYSTEM WARNING" not in result.message.content
    assert "Error executing" in result.message.content
