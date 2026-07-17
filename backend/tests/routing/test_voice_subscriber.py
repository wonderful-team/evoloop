"""VoiceResultSubscriber (design §16.4): pushback via lifecycle events, not finish.

Mocks only ``manager.push`` at the fixture boundary and asserts that the right
``voice.route_result`` is pushed for voice-originated threads and nothing for
non-voice threads.
"""

from __future__ import annotations

import pytest

from app.core.engine.event.schemas import AgentRunCompletedEvent
from app.core.events.schemas.lifecycle import (
    SessionCompletedData,
    SessionCompletedEvent,
)
from app.core.routing import executor
from app.core.routing.subscribers import VoiceResultSubscriber


class _FakeManager:
    def __init__(self):
        self.pushes = []

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


def _setup(monkeypatch):
    fake = _FakeManager()
    monkeypatch.setattr(executor, "manager", fake)
    return fake, VoiceResultSubscriber()


def _last(fake):
    tid, env = fake.pushes[-1]
    return tid, env["body"]["status"], env["body"]["summary"]


def _session_completed(tid, summary):
    return SessionCompletedEvent(data=SessionCompletedData(thread_id=tid, summary=summary))


def _run_completed(tid, status, summary=""):
    return AgentRunCompletedEvent(thread_id=tid, status=status, payload={"summary": summary})


@pytest.mark.asyncio
async def test_session_completed_voice_pushes_done(monkeypatch):
    fake, sub = _setup(monkeypatch)
    await executor._mark_voice("v1", "agent")

    await sub.on_session_completed(_session_completed("v1", "搞定了"))

    assert fake.pushes and _last(fake) == ("v1", "done", "搞定了")
    assert await executor.consume_voice("v1") is None, "mark consumed exactly once"


@pytest.mark.asyncio
async def test_session_completed_non_voice_noop(monkeypatch):
    fake, sub = _setup(monkeypatch)

    await sub.on_session_completed(_session_completed("other", "x"))

    assert fake.pushes == []


@pytest.mark.asyncio
async def test_run_completed_failed_voice_pushes_failed(monkeypatch):
    fake, sub = _setup(monkeypatch)
    await executor._mark_voice("v2", "agent")

    await sub.on_run_completed(_run_completed("v2", "failed", "LLM 404"))

    assert fake.pushes and _last(fake) == ("v2", "failed", "LLM 404")


@pytest.mark.asyncio
async def test_run_completed_done_ignored(monkeypatch):
    fake, sub = _setup(monkeypatch)
    await executor._mark_voice("v3", "agent")

    await sub.on_run_completed(_run_completed("v3", "done", "should not push"))

    assert fake.pushes == [], "success is delivered via session_completed, not run_completed"
    assert await executor.consume_voice("v3") == "agent", "mark left for session_completed"


@pytest.mark.asyncio
async def test_run_completed_failed_non_voice_noop(monkeypatch):
    fake, sub = _setup(monkeypatch)

    await sub.on_run_completed(_run_completed("other", "failed", "err"))

    assert fake.pushes == []
