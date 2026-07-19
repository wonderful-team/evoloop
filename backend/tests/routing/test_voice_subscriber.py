"""VoiceChannel (replaces VoiceResultSubscriber): pushback via Channel.send().

Mocks only ``executor.push_voice_result`` at the fixture boundary and asserts
that the right ``voice.route_result`` is pushed for voice-sourced events and
nothing for non-voice events.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.channel import ChannelContext
from app.core.channel.voice_channel import VoiceChannel
from app.core.engine.event.schemas import AgentRunCompletedEvent
from app.core.events.schemas.lifecycle import (
    SessionCompletedData,
    SessionCompletedEvent,
)
from app.core.routing import executor


def _session_completed(tid, summary, source="voice"):
    return SessionCompletedEvent(
        data=SessionCompletedData(thread_id=tid, summary=summary, source=source)
    )


def _run_completed(tid, status, source="voice", summary=""):
    return AgentRunCompletedEvent(
        thread_id=tid, status=status, source=source,
        payload={"summary": summary},
    )


def _ctx(tid):
    return ChannelContext(thread_id=tid)


@pytest.mark.asyncio
async def test_session_completed_voice_pushes_done(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: pushed.append((tid, status, summary))),
    )
    ch = VoiceChannel()

    await ch.send(_session_completed("v1", "搞定了"), _ctx("v1"))

    assert pushed == [("v1", "done", "搞定了")]


@pytest.mark.asyncio
async def test_session_completed_non_voice_noop(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: pushed.append((tid, status, summary))),
    )
    ch = VoiceChannel()

    await ch.send(_session_completed("other", "x", source=""), _ctx("other"))

    assert pushed == []


@pytest.mark.asyncio
async def test_run_completed_failed_voice_pushes_failed(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: pushed.append((tid, status, summary))),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("v2", "failed", summary="LLM 404"), _ctx("v2"))

    assert pushed == [("v2", "failed", "LLM 404")]


@pytest.mark.asyncio
async def test_run_completed_done_ignored(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: pushed.append((tid, status, summary))),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("v3", "done"), _ctx("v3"))

    assert pushed == [], "success is delivered via session_completed, not run_completed"


@pytest.mark.asyncio
async def test_run_completed_failed_non_voice_noop(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: pushed.append((tid, status, summary))),
    )
    ch = VoiceChannel()

    await ch.send(_run_completed("other", "failed", source=""), _ctx("other"))

    assert pushed == []


from app.core.engine.message.schemas import MessageBlock
from app.models.schemas.events import TokenEvent

@pytest.mark.asyncio
async def test_token_streaming_and_sentence_split(monkeypatch):
    tokens_pushed = []
    boundaries_pushed = []
    results_pushed = []

    monkeypatch.setattr(
        executor, "push_voice_token",
        AsyncMock(side_effect=lambda tid, token, idx: tokens_pushed.append((tid, token))),
    )
    monkeypatch.setattr(
        executor, "push_voice_tts_boundary",
        AsyncMock(side_effect=lambda tid, sentence, idx: boundaries_pushed.append((tid, sentence))),
    )
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: results_pushed.append((tid, status, summary))),
    )

    executor._voice_registry["v_stream"] = "default"
    try:
        ch = VoiceChannel()

        await ch.send(TokenEvent(thread_id="v_stream", content="你好"), _ctx("v_stream"))
        await ch.send(TokenEvent(thread_id="v_stream", content="，"), _ctx("v_stream"))
        await ch.send(TokenEvent(thread_id="v_stream", content="世界。"), _ctx("v_stream"))

        assert tokens_pushed == [("v_stream", "你好"), ("v_stream", "，"), ("v_stream", "世界。")]
        assert boundaries_pushed == [("v_stream", "你好，世界。")]

        await ch.send(MessageBlock(id="msg-1", thread_id="v_stream", role="ai", content="你好，世界。"), _ctx("v_stream"))
        assert results_pushed == [("v_stream", "routed", "")]

        await ch.send(_session_completed("v_stream", "你好，世界。"), _ctx("v_stream"))
        assert results_pushed == [("v_stream", "routed", ""), ("v_stream", "done", "")]
    finally:
        executor._voice_registry.pop("v_stream", None)


@pytest.mark.asyncio
async def test_token_streaming_and_non_duplicate_done(monkeypatch):
    tokens_pushed = []
    boundaries_pushed = []
    results_pushed = []

    monkeypatch.setattr(
        executor, "push_voice_token",
        AsyncMock(side_effect=lambda tid, token, idx: tokens_pushed.append((tid, token))),
    )
    monkeypatch.setattr(
        executor, "push_voice_tts_boundary",
        AsyncMock(side_effect=lambda tid, sentence, idx: boundaries_pushed.append((tid, sentence))),
    )
    monkeypatch.setattr(
        executor, "push_voice_result",
        AsyncMock(side_effect=lambda tid, status, summary: results_pushed.append((tid, status, summary))),
    )

    executor._voice_registry["v_stream2"] = "default"
    try:
        ch = VoiceChannel()

        await ch.send(TokenEvent(thread_id="v_stream2", content="好的，我来处理。"), _ctx("v_stream2"))
        assert boundaries_pushed == [("v_stream2", "好的，我来处理。")]

        await ch.send(MessageBlock(id="msg-2", thread_id="v_stream2", role="ai", content="好的，我来处理。"), _ctx("v_stream2"))
        assert results_pushed == [("v_stream2", "routed", "")]

        await ch.send(_session_completed("v_stream2", "我已经执行完毕。"), _ctx("v_stream2"))
        assert results_pushed == [("v_stream2", "routed", ""), ("v_stream2", "done", "我已经执行完毕。")]
    finally:
        executor._voice_registry.pop("v_stream2", None)


@pytest.mark.asyncio
async def test_token_streaming_through_publisher_voice_channel(monkeypatch):
    """Full chain: MessagePublisher -> channel_registry -> VoiceChannel -> push_voice_tts_boundary."""
    tokens_pushed = []
    boundaries_pushed = []

    monkeypatch.setattr(
        executor, "push_voice_token",
        AsyncMock(side_effect=lambda tid, token, idx: tokens_pushed.append((tid, token))),
    )
    monkeypatch.setattr(
        executor, "push_voice_tts_boundary",
        AsyncMock(side_effect=lambda tid, sentence, idx: boundaries_pushed.append((tid, sentence))),
    )

    executor._voice_registry["v_pub"] = "agent"
    try:
        from app.core.engine.message.publisher import MessagePublisher

        pub = MessagePublisher(thread_id="v_pub")
        await pub.publish(TokenEvent(thread_id="v_pub", content="今天天气"))
        await pub.publish(TokenEvent(thread_id="v_pub", content="真不错。"))

        assert boundaries_pushed == [("v_pub", "今天天气真不错。")]
        assert len(tokens_pushed) == 2
    finally:
        executor._voice_registry.pop("v_pub", None)


@pytest.mark.asyncio
async def test_token_streaming_non_voice_ignored_by_publisher(monkeypatch):
    """Non-voice thread should NOT route TokenEvent to VoiceChannel."""
    boundaries_pushed = []

    monkeypatch.setattr(
        executor, "push_voice_tts_boundary",
        AsyncMock(side_effect=lambda tid, sentence, idx: boundaries_pushed.append((tid, sentence))),
    )

    from app.core.engine.message.publisher import MessagePublisher

    pub = MessagePublisher(thread_id="non-voice-thread")
    await pub.publish(TokenEvent(thread_id="non-voice-thread", content="你好。"))

    assert boundaries_pushed == []
