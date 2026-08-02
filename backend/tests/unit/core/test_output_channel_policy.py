
from app.core.channel.policy import OutputChannelPolicy
from app.core.engine.message.schemas import MessageBlock
from app.core.events.base import BaseEvent
from app.models.schemas.events import (
    ProgressEvent,
    ThinkingEvent,
    TokenEvent,
)


class FakeBaseEvent(BaseEvent):
    type_name: str = "fake.event"
    thread_id: str = "t1"
    is_public: bool = True
    source: str = "voice"


# ── Stream events (TokenEvent / ThinkingEvent / ProgressEvent) ─────────────────

def test_resolve_token_event_voice_supervisor():
    res = OutputChannelPolicy.resolve(
        TokenEvent(thread_id="t1", content="ok"),
        session_source="voice",
        node_source="supervisor",
    )
    assert res == {"sse", "voice"}


def test_resolve_token_event_voice_worker():
    res = OutputChannelPolicy.resolve(
        TokenEvent(thread_id="t1", content="ok"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse"}


def test_resolve_token_event_web_supervisor():
    res = OutputChannelPolicy.resolve(
        TokenEvent(thread_id="t1", content="ok"),
        session_source="web",
        node_source="supervisor",
    )
    assert res == {"sse"}


def test_resolve_thinking_event_voice_worker():
    res = OutputChannelPolicy.resolve(
        ThinkingEvent(thread_id="t1", content="thinking"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse"}


def test_resolve_progress_event_voice_supervisor():
    res = OutputChannelPolicy.resolve(
        ProgressEvent(thread_id="t1", message="running"),
        session_source="voice",
        node_source="supervisor",
    )
    assert res == {"sse", "voice"}


# ── AI MessageBlock (status-aware) ─────────────────────────────────────────────

def _ai_block(status: str) -> MessageBlock:
    return MessageBlock(
        id="m1",
        thread_id="t1",
        role="ai",
        content="hello",
        status=status,
    )


def test_resolve_ai_block_completed_voice_supervisor():
    res = OutputChannelPolicy.resolve(
        _ai_block("completed"),
        session_source="voice",
        node_source="supervisor",
    )
    assert res == {"sse", "mobile", "voice"}


def test_resolve_ai_block_completed_voice_worker():
    res = OutputChannelPolicy.resolve(
        _ai_block("completed"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse", "mobile"}


def test_resolve_ai_block_completed_web_supervisor():
    res = OutputChannelPolicy.resolve(
        _ai_block("completed"),
        session_source="web",
        node_source="supervisor",
    )
    assert res == {"sse", "mobile"}


def test_resolve_ai_block_streaming_voice_supervisor():
    res = OutputChannelPolicy.resolve(
        _ai_block("streaming"),
        session_source="voice",
        node_source="supervisor",
    )
    assert res == {"sse", "voice"}


def test_resolve_ai_block_streaming_voice_worker():
    res = OutputChannelPolicy.resolve(
        _ai_block("streaming"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse"}


def test_resolve_ai_block_streaming_web_supervisor():
    res = OutputChannelPolicy.resolve(
        _ai_block("streaming"),
        session_source="web",
        node_source="supervisor",
    )
    assert res == {"sse"}


def test_resolve_ai_block_finish_node():
    # finish node AI messages should not go to voice
    res = OutputChannelPolicy.resolve(
        _ai_block("completed"),
        session_source="voice",
        node_source="finish",
    )
    assert res == {"sse", "mobile"}


# ── Tool MessageBlock (status-aware) ─────────────────────────────────────────

def _tool_block(status: str) -> MessageBlock:
    return MessageBlock(
        id="m1",
        thread_id="t1",
        role="tool",
        content="tool output",
        status=status,
    )


def test_resolve_tool_block_completed():
    res = OutputChannelPolicy.resolve(
        _tool_block("completed"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse", "mobile"}


def test_resolve_tool_block_streaming():
    res = OutputChannelPolicy.resolve(
        _tool_block("streaming"),
        session_source="voice",
        node_source="worker",
    )
    assert res == {"sse"}


# ── Human MessageBlock (mobile dedup) ─────────────────────────────────────────

def _human_block(source: str | None = None) -> MessageBlock:
    return MessageBlock(
        id="m1",
        thread_id="t1",
        role="human",
        content="hi",
        status="completed",
        source=source,
    )


def test_resolve_human_block_mobile_source_no_mobile_channel():
    # Mobile gateway already pushes the original message to mobile;
    # desktop side should not echo it back.
    res = OutputChannelPolicy.resolve(
        _human_block(),
        session_source="mobile",
        node_source=None,
    )
    assert res == {"sse"}


def test_resolve_human_block_web_source_includes_mobile():
    res = OutputChannelPolicy.resolve(
        _human_block(),
        session_source="web",
        node_source=None,
    )
    assert res == {"sse", "mobile"}


# ── BaseEvent ─────────────────────────────────────────────────────────────────

def test_resolve_base_event_voice():
    event = FakeBaseEvent()
    res = OutputChannelPolicy.resolve(
        event,
        session_source="voice",
        node_source=None,
    )
    assert res == {"sse", "voice"}


def test_resolve_base_event_web():
    event = FakeBaseEvent(source="web")
    res = OutputChannelPolicy.resolve(
        event,
        session_source="web",
        node_source=None,
    )
    assert res == {"sse"}


def test_resolve_base_event_override_source():
    class EventWithSource(BaseEvent):
        type_name: str = "fake.event"
        thread_id: str = "t1"
        is_public: bool = True
        source: str = "voice"

    event = EventWithSource()
    res = OutputChannelPolicy.resolve(
        event,
        session_source="web",
        node_source=None,
    )
    assert res == {"sse", "voice"}


def test_resolve_base_event_source_reversal():
    # event.source takes precedence over session_source.
    class EventWithSource(BaseEvent):
        type_name: str = "fake.event"
        thread_id: str = "t1"
        is_public: bool = True
        source: str = "web"

    event = EventWithSource()
    res = OutputChannelPolicy.resolve(
        event,
        session_source="voice",
        node_source=None,
    )
    assert res == {"sse"}


# ── Unknown payload fallback ─────────────────────────────────────────────────

def test_resolve_unknown_payload_defaults_to_sse():
    res = OutputChannelPolicy.resolve(
        object(),
        session_source="voice",
        node_source="supervisor",
    )
    assert res == {"sse"}
