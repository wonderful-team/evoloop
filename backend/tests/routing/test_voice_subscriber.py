"""VoiceChannel routing tests: verify Channel.send() pushes voice results.

Mocks ``VoiceChannel`` transport class methods and asserts that the right
``voice.route_result`` is pushed for voice-sourced events and nothing for
non-voice events.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.channel import ChannelContext
from app.core.channel.output.voice_channel import VoiceChannel
from app.core.engine.event.schemas import AgentRunCompletedEvent
from app.core.engine.message.schemas import MessageBlock
from app.core.events.schemas.lifecycle import (
    SessionCompletedData,
    SessionCompletedEvent,
)
from app.models.schemas.events import TokenEvent


@pytest.fixture(autouse=True)
def _stub_message_broker(monkeypatch):
    """Ensure the WebChannel broker.publish is awaitable regardless of what
    earlier tests may have left patched.
    """
    from app.core.channel.output import web_channel

    broker = MagicMock()
    broker.publish = AsyncMock()
    monkeypatch.setattr(web_channel, "get_message_broker", lambda: broker)
    yield


def _session_completed(tid, summary, source="voice"):
    return SessionCompletedEvent(
        data=SessionCompletedData(
            thread_id=tid, summary=summary, tts_summary=summary, source=source
        )
    )


def _run_completed(tid, status, source="voice", summary=""):
    return AgentRunCompletedEvent(
        thread_id=tid,
        status=status,
        source=source,
        payload={"summary": summary},
    )


def _ctx(tid):
    return ChannelContext(thread_id=tid)


@pytest.mark.asyncio
async def test_session_completed_voice_pushes_done(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: pushed.append(
                (tid, status, summary)
            )
        ),
    )
    ch = VoiceChannel()

    await ch.send(_session_completed("v1", "搞定了"), _ctx("v1"))

    assert pushed == [("v1", "done", "搞定了")]


@pytest.mark.asyncio
async def test_session_completed_non_voice_noop(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: pushed.append(
                (tid, status, summary)
            )
        ),
    )
    ch = VoiceChannel()

    await ch.send(_session_completed("other", "x", source=""), _ctx("other"))

    assert pushed == []


@pytest.mark.asyncio
async def test_run_completed_failed_voice_pushes_failed(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: pushed.append(
                (tid, status, summary)
            )
        ),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("v2", "failed", summary="LLM 404"), _ctx("v2"))

    assert pushed == [("v2", "failed", "LLM 404")]


@pytest.mark.asyncio
async def test_run_completed_done_ignored(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: pushed.append(
                (tid, status, summary)
            )
        ),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("v3", "done"), _ctx("v3"))

    assert pushed == [], "success is delivered via session_completed, not run_completed"


@pytest.mark.asyncio
async def test_run_completed_failed_non_voice_noop(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: pushed.append(
                (tid, status, summary)
            )
        ),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("other", "failed", source=""), _ctx("other"))

    assert pushed == []


@pytest.mark.asyncio
async def test_token_streaming_and_sentence_split(monkeypatch):
    tts_chunks_pushed = []
    boundaries_pushed = []
    results_pushed = []

    async def _record_tts_chunk(tid, text, end, *, _force_start=False):
        tts_chunks_pushed.append((tid, text, end))

    monkeypatch.setattr(
        VoiceChannel,
        "push_tts_chunk",
        AsyncMock(side_effect=_record_tts_chunk),
    )
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_tts_boundary",
        AsyncMock(
            side_effect=lambda tid, sentence, idx: boundaries_pushed.append(
                (tid, sentence)
            )
        ),
    )
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: results_pushed.append(
                (tid, status, summary)
            )
        ),
    )

    # Simulate voice session via ContextVar (replaces _voice_registry injection)
    from app.core.channel.policy import current_session_source
    token = current_session_source.set("voice")
    try:
        ch = VoiceChannel()

        await ch.send(
            TokenEvent(thread_id="v_stream", content="你好"), _ctx("v_stream")
        )
        await ch.send(TokenEvent(thread_id="v_stream", content="，"), _ctx("v_stream"))
        await ch.send(
            TokenEvent(thread_id="v_stream", content="世界。"), _ctx("v_stream")
        )

        assert tts_chunks_pushed == [("v_stream", "你好，世界。", False)]
        assert boundaries_pushed == []

        await ch.send(
            MessageBlock(
                id="msg-1", thread_id="v_stream", role="ai", content="你好，世界。"
            ),
            _ctx("v_stream"),
        )
        await asyncio.sleep(0)
        assert results_pushed == [("v_stream", "routed", "")]

        await ch.send(_session_completed("v_stream", "你好，世界。"), _ctx("v_stream"))
        assert results_pushed == [
            ("v_stream", "routed", ""),
            ("v_stream", "done", "你好，世界。"),
        ]
    finally:
        current_session_source.reset(token)


@pytest.mark.asyncio
async def test_token_streaming_and_non_duplicate_done(monkeypatch):
    tts_chunks_pushed = []
    boundaries_pushed = []
    results_pushed = []

    async def _record_tts_chunk(tid, text, end, *, _force_start=False):
        tts_chunks_pushed.append((tid, text, end))

    monkeypatch.setattr(
        VoiceChannel,
        "push_tts_chunk",
        AsyncMock(side_effect=_record_tts_chunk),
    )
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_tts_boundary",
        AsyncMock(
            side_effect=lambda tid, sentence, idx: boundaries_pushed.append(
                (tid, sentence)
            )
        ),
    )
    monkeypatch.setattr(
        VoiceChannel,
        "push_voice_result",
        AsyncMock(
            side_effect=lambda tid, status, summary, **kwargs: results_pushed.append(
                (tid, status, summary)
            )
        ),
    )

    # Simulate voice session via ContextVar (replaces _voice_registry injection)
    from app.core.channel.policy import current_session_source
    token = current_session_source.set("voice")
    try:
        ch = VoiceChannel()

        await ch.send(
            TokenEvent(thread_id="v_stream2", content="好的，我来处理。"),
            _ctx("v_stream2"),
        )
        assert tts_chunks_pushed == [("v_stream2", "好的，我来处理。", False)]
        assert boundaries_pushed == []

        await ch.send(
            MessageBlock(
                id="msg-2", thread_id="v_stream2", role="ai", content="好的，我来处理。"
            ),
            _ctx("v_stream2"),
        )
        await asyncio.sleep(0)
        assert results_pushed == [("v_stream2", "routed", "")]

        await ch.send(
            _session_completed("v_stream2", "我已经执行完毕。"), _ctx("v_stream2")
        )
        assert results_pushed == [
            ("v_stream2", "routed", ""),
            ("v_stream2", "done", "我已经执行完毕。"),
        ]
    finally:
        current_session_source.reset(token)


@pytest.mark.asyncio
async def test_token_streaming_through_publisher_voice_channel(monkeypatch):
    """TokenEvent via Publisher for non-supervisor node → SSE only (no VoiceChannel TTS)."""
    from app.core.channel.output.voice_channel import VoiceChannel

    push_tts_chunk_mock = AsyncMock()
    monkeypatch.setattr(VoiceChannel, "push_tts_chunk", push_tts_chunk_mock)

    # Simulate voice session + worker node: TokenEvent should NOT reach VoiceChannel
    from app.core.channel.policy import current_session_source
    from app.core.engine.callbacks.database_logger import current_node_source
    s_token = current_session_source.set("voice")
    n_token = current_node_source.set("worker")
    try:
        from app.core.engine.message.publisher import MessagePublisher

        pub = MessagePublisher(thread_id="v_pub")
        await pub.publish(TokenEvent(thread_id="v_pub", content="今天天气"))
        await pub.publish(TokenEvent(thread_id="v_pub", content="真不错。"))

        # worker node_source → voice channel excluded by OutputChannelPolicy
        push_tts_chunk_mock.assert_not_awaited()
    finally:
        current_session_source.reset(s_token)
        current_node_source.reset(n_token)


@pytest.mark.asyncio
async def test_token_streaming_non_voice_ignored_by_publisher(monkeypatch):
    """Non-voice thread should NOT route TokenEvent to VoiceChannel."""
    from app.core.channel.output.voice_channel import VoiceChannel

    push_tts_chunk_mock = AsyncMock()
    monkeypatch.setattr(VoiceChannel, "push_tts_chunk", push_tts_chunk_mock)

    from app.core.engine.message.publisher import MessagePublisher

    pub = MessagePublisher(thread_id="non-voice-thread")
    await pub.publish(TokenEvent(thread_id="non-voice-thread", content="你好。"))

    push_tts_chunk_mock.assert_not_awaited()
