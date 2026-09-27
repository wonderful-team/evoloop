from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from litellm.types.utils import ModelResponseStream

from app.core.engine.sdk_adapter.events import SDKEventBridge


def _bridge(config: dict) -> SDKEventBridge:
    return SDKEventBridge(config=config, thread_id="sse-test")


def _chunk(**delta_kwargs: object) -> ModelResponseStream:
    return ModelResponseStream(
        id="chatcmpl-1", created=0, model="test", choices=[{"delta": dict(delta_kwargs)}]
    )


@pytest.mark.asyncio
async def test_on_token_routes_content_to_token_stream_and_reasoning_to_thinking() -> None:
    config = {
        "configurable": {"run_id": "run-1"},
        "callbacks": [
            SimpleNamespace(on_llm_new_token=AsyncMock(), emit_thinking=AsyncMock())
        ],
    }
    bridge = _bridge(config)

    # Tokens should be attributed to the real AI message id, not the run_id.
    from unittest.mock import patch

    with patch(
        "app.core.context.manager.ContextManager.current",
        return_value=SimpleNamespace(last_ai_message_id="msg-ai-1"),
    ):
        bridge.on_token(_chunk(content="hello"))
        bridge.on_token(_chunk(reasoning_content="thinking..."))
        bridge.on_token(_chunk())  # empty delta ignored
        await asyncio.gather(*tuple(bridge._tasks))

    callback = config["callbacks"][0]
    callback.on_llm_new_token.assert_awaited_once()
    assert callback.on_llm_new_token.await_args.kwargs["token"] == "hello"
    # The legacy callback pipeline uses run_id for the token attribution id;
    # after F4 it carries the real AI message id instead of the SDK run_id.
    assert callback.on_llm_new_token.await_args.kwargs["run_id"] == "msg-ai-1"
    callback.emit_thinking.assert_awaited_once_with("thinking...", message_id="msg-ai-1")


@pytest.mark.asyncio
async def test_on_token_suppresses_tool_call_deltas() -> None:
    config = {
        "configurable": {"run_id": "run-1"},
        "callbacks": [SimpleNamespace(on_llm_new_token=AsyncMock())],
    }
    bridge = _bridge(config)

    bridge.on_token(
        _chunk(
            tool_calls=[
                SimpleNamespace(index=0, id="c1", function=SimpleNamespace(name="bash", arguments="{"))
            ]
        )
    )
    await asyncio.gather(*tuple(bridge._tasks))

    config["callbacks"][0].on_llm_new_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_agent_message_flushes_stream_buffers() -> None:
    handler = AsyncMock()
    stream_cb = SimpleNamespace(
        flush_stream_buffers=AsyncMock(),
        thread_id="sse-test",
    )
    config = {
        "configurable": {"run_id": "run-9", "message_handler": handler},
        "callbacks": [stream_cb],
        "metadata": {},
    }
    bridge = _bridge(config)

    from openhands.sdk.event import MessageEvent
    from openhands.sdk.llm import Message, TextContent

    event = MessageEvent(
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="done")]),
    )
    await bridge._persist_agent_message(event)
    await asyncio.gather(*tuple(bridge._tasks))

    handler.handle_ai_message.assert_awaited_once()
    stream_cb.flush_stream_buffers.assert_awaited_once_with("run-9")
