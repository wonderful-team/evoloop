from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.react import completion
from app.core.engine.sdk_adapter import session_bridge
from app.core.engine.state import AgentState


@pytest.mark.asyncio
async def test_run_turn_uses_persisted_sdk_conversation(monkeypatch, tmp_path) -> None:
    ctx = EvoContext(
        thread_id="sdk-test-thread",
        working_directory=str(tmp_path),
    )
    ContextManager.set(ctx)
    monkeypatch.setattr(
        session_bridge,
        "create_sdk_llm",
        AsyncMock(
            return_value=TestLLM.from_messages(
                [Message(role="assistant", content=[TextContent(text="done")])]
            )
        ),
    )
    monkeypatch.setattr(
        session_bridge,
        "build_sdk_tools",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        session_bridge,
        "build_system_prompt",
        AsyncMock(return_value="test system"),
    )
    monkeypatch.setattr(completion, "publish_session_completed_react", AsyncMock())
    monkeypatch.setattr(session_bridge.settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path))
    message_handler = AsyncMock()

    result = await session_bridge.run_turn(
        state=AgentState(
            thread_id="sdk-test-thread",
            messages=[HumanMessage(content="hello")],
        ),
        config={
            "configurable": {
                "thread_id": "sdk-test-thread",
                "model": "test",
                "message_handler": message_handler,
            },
            "metadata": {},
        },
        thread_id="sdk-test-thread",
        max_steps=2,
    )

    assert result["outcome"] == "success"
    assert result["is_truncated"] is False
    assert (tmp_path / "sdk-conversations").exists()
    message_handler.handle_ai_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_turn_retries_once_on_auth_failure(monkeypatch, tmp_path) -> None:
    from openhands.sdk.llm.exceptions.types import LLMAuthenticationError

    ctx = EvoContext(
        thread_id="sdk-auth-retry",
        working_directory=str(tmp_path),
    )
    ContextManager.set(ctx)
    llm = TestLLM.from_messages(
        [
            LLMAuthenticationError("bad key"),
            Message(role="assistant", content=[TextContent(text="done")]),
        ]
    )
    create_llm = AsyncMock(return_value=llm)
    monkeypatch.setattr(session_bridge, "create_sdk_llm", create_llm)
    monkeypatch.setattr(session_bridge, "build_sdk_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        session_bridge, "build_system_prompt", AsyncMock(return_value="test system")
    )
    monkeypatch.setattr(completion, "publish_session_completed_react", AsyncMock())
    monkeypatch.setattr(session_bridge.settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path))

    result = await session_bridge.run_turn(
        state=AgentState(
            thread_id="sdk-auth-retry",
            messages=[HumanMessage(content="hello")],
        ),
        config={
            "configurable": {"thread_id": "sdk-auth-retry", "model": "test"},
            "metadata": {},
        },
        thread_id="sdk-auth-retry",
        max_steps=2,
    )

    assert result["outcome"] == "success"
    assert create_llm.await_count == 2


@pytest.mark.asyncio
async def test_ask_human_on_stuck_raises_interrupt(monkeypatch) -> None:
    from app.core.exceptions import AgentHumanInterruptException
    from app.core.hitl import core as hitl_core

    async def fake_create_request(**_: object) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(id="req-1", prompt="停止/继续", default_value="停止")

    async def fake_push(**_: object) -> None:
        return None

    def fake_raise(_request_id: str, _text: str) -> None:
        raise AgentHumanInterruptException("req-1", "选择停止或继续")

    monkeypatch.setattr(hitl_core, "create_request", fake_create_request)
    monkeypatch.setattr(hitl_core, "push_hitl_notification", fake_push)
    monkeypatch.setattr(hitl_core, "raise_hitl_interrupt", fake_raise)

    with pytest.raises(AgentHumanInterruptException):
        await session_bridge._ask_human_on_stuck(
            "sdk-stuck-thread", AgentState(thread_id="sdk-stuck-thread")
        )


@pytest.mark.asyncio
async def test_ask_human_on_stuck_falls_back_to_stop(monkeypatch) -> None:
    from app.core.hitl import core as hitl_core

    async def failing_create_request(**_: object) -> object:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(hitl_core, "create_request", failing_create_request)

    decision = await session_bridge._ask_human_on_stuck(
        "sdk-stuck-thread", AgentState(thread_id="sdk-stuck-thread")
    )

    assert decision == "stop"
