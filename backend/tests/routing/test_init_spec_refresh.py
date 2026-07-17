"""Init Spec event-triggered refresh (design §19.6): skill events -> debounced rebuild."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.routing import subscribers, tasks


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    ["on_skill_created", "on_skill_updated", "on_skill_deleted"],
)
async def test_skill_event_triggers_schedule(handler: str, monkeypatch) -> None:
    sched = AsyncMock()
    monkeypatch.setattr(subscribers, "schedule_init_spec_rebuild", sched)

    await getattr(subscribers.InitSpecRefreshSubscriber(), handler)(SimpleNamespace(data={}))

    sched.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_debounce_coalesces_burst_into_one_rebuild(monkeypatch) -> None:
    # isolate module globals (loop-bound lock + pending task)
    monkeypatch.setattr(subscribers, "_debounce_lock", asyncio.Lock())
    monkeypatch.setattr(subscribers, "_debounce_task", None)
    monkeypatch.setattr(subscribers, "_debounce_seconds", lambda: 0.02)
    delay = Mock()
    monkeypatch.setattr(tasks.build_voice_init_spec, "delay", delay)

    for _ in range(5):
        await subscribers.schedule_init_spec_rebuild()
    await asyncio.sleep(0.06)  # let the single debounced task fire

    assert delay.call_count == 1  # 5 events coalesced into 1 rebuild


@pytest.mark.unit
def test_periodic_fallback_still_enqueues(monkeypatch) -> None:
    delay = Mock()
    monkeypatch.setattr(tasks.build_voice_init_spec, "delay", delay)

    tasks.build_voice_init_spec_periodic()

    delay.assert_called_once()
