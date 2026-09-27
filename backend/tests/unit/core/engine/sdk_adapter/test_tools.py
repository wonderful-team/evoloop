from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.engine.sdk_adapter.tools import _build_sdk_tool
from app.core.exceptions import AgentHumanInterruptException


class _Result:
    class _Message:
        content = "native result"

    message = _Message()


class _NativeExecutor:
    async def execute_tool(self, **_: object) -> _Result:
        return _Result()


class _InterruptingExecutor:
    config = {"configurable": {"thread_id": "hitl-thread", "model": "test"}}
    state = SimpleNamespace()

    async def execute_tool(self, **_: object) -> _Result:
        raise AgentHumanInterruptException("wait for approval")


@pytest.mark.asyncio
async def test_client_tool_adapter_runs_native_executor_from_worker_thread() -> None:
    tool = SimpleNamespace(
        name="demo",
        description="Demo tool",
        raw_args_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    sdk_tool = _build_sdk_tool(
        tool,
        loop=asyncio.get_running_loop(),
        native_executor=_NativeExecutor(),
        tool_history=[],
    )

    action = sdk_tool.action_from_arguments({"value": "x"})
    observation = await asyncio.to_thread(sdk_tool.executor, action)

    assert sdk_tool.name == "demo"
    assert observation.text == "native result"


@pytest.mark.asyncio
async def test_client_tool_adapter_routes_human_resume_without_sdk_send_message(
    monkeypatch,
) -> None:
    class Gate:
        async def wait_next(self):
            return SimpleNamespace(
                kind="user_message",
                payload={"hitl_resume_response": "approved"},
            )

    fake_session = SimpleNamespace(gate=Gate())
    monkeypatch.setattr(
        "app.core.engine.session.manager.session_manager.get",
        lambda _thread_id: fake_session,
    )
    monkeypatch.setattr(
        "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
        AsyncMock(return_value=None),
    )

    tool = SimpleNamespace(
        name="ask_confirm",
        description="Ask for confirmation",
        raw_args_schema={"type": "object", "properties": {}},
    )
    sdk_tool = _build_sdk_tool(
        tool,
        loop=asyncio.get_running_loop(),
        native_executor=_InterruptingExecutor(),
        tool_history=[],
    )
    action = sdk_tool.action_from_arguments({})
    observation = await asyncio.to_thread(sdk_tool.executor, action)

    assert observation.text == "approved"
