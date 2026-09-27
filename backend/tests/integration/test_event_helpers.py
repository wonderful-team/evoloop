"""Verification of event publisher/subscriber helper consolidation.

- publish_app_map_created/superseded → _publish_app_map_event
- on_skill_mutated/on_macro_mutated → _schedule_matcher_rebuild
"""

from __future__ import annotations

from app.core.atlas.source.event import publishers as atlas_publishers
from app.core.atlas.source.event.schemas import AppMapEvent
from app.core.learning.event import subscribers as learning_subscribers


class _Bus:
    """Minimal async bus double that records published events."""

    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event, **kwargs) -> None:
        self.published.append(event)


class TestPublishAppMapEvents:
    async def test_created_event(self, monkeypatch) -> None:
        bus = _Bus()
        monkeypatch.setattr(atlas_publishers, "system_bus", bus)
        await atlas_publishers.publish_app_map_created(
            app_map_id=1, project_id=2, entity="com.a", map_version=3,
            content_hash="h", thread_id="th-1",
        )
        (ev,) = bus.published
        assert isinstance(ev, AppMapEvent)
        assert ev.action == "created"
        assert ev.app_map_id == 1
        assert ev.project_id == 2
        assert ev.entity == "com.a"
        assert ev.map_version == 3
        assert ev.content_hash == "h"
        assert ev.thread_id == "th-1"

    async def test_superseded_event(self, monkeypatch) -> None:
        bus = _Bus()
        monkeypatch.setattr(atlas_publishers, "system_bus", bus)
        await atlas_publishers.publish_app_map_superseded(
            app_map_id=1, project_id=2, entity="com.a", map_version=3,
            content_hash="h", superseded_by=99,
        )
        (ev,) = bus.published
        assert ev.action == "superseded"
        assert ev.superseded_by == 99


class _MatcherCache:
    def __init__(self) -> None:
        self.calls = 0

    async def invalidate_and_schedule_rebuild(self) -> None:
        self.calls += 1


class _SubscriberStub:
    """Stand-in exposing _schedule_matcher_rebuild with a logger."""

    def __init__(self) -> None:
        self._logger = learning_subscribers.logger

    async def _schedule_matcher_rebuild(self, event, kind: str, id_key: str) -> None:
        from app.core.routing.matcher_cache import matcher_cache

        await matcher_cache.invalidate_and_schedule_rebuild()


class TestScheduleMatcherRebuild:
    async def test_invalidates_cache(self, monkeypatch) -> None:
        mc = _MatcherCache()
        monkeypatch.setattr("app.core.routing.matcher_cache.matcher_cache", mc)

        stub = _SubscriberStub()
        event = type("Ev", (), {"event_type": "created", "data": {"skill_id": 5}})()
        await stub._schedule_matcher_rebuild(event, "skill", "skill_id")

        assert mc.calls == 1

    async def test_subscribers_delegate_to_helper(self, monkeypatch) -> None:
        mc = _MatcherCache()
        monkeypatch.setattr("app.core.routing.matcher_cache.matcher_cache", mc)

        # Patch the real class method to assert delegation + id key.
        real = learning_subscribers.InitSpecRefreshSubscriber._schedule_matcher_rebuild
        calls: list[tuple] = []

        async def spy(self, event, kind, id_key) -> None:
            calls.append((kind, id_key))
            await real(self, event, kind, id_key)

        monkeypatch.setattr(
            learning_subscribers.InitSpecRefreshSubscriber,
            "_schedule_matcher_rebuild",
            spy,
        )

        sub = learning_subscribers.InitSpecRefreshSubscriber()
        skill_event = type("Ev", (), {"event_type": "created", "data": {"skill_id": 5}})()
        macro_event = type("Ev", (), {"event_type": "updated", "data": {"macro_id": 7}})()
        await sub.on_skill_mutated(skill_event)
        await sub.on_macro_mutated(macro_event)

        assert ("skill", "skill_id") in calls
        assert ("macro", "macro_id") in calls
        assert mc.calls == 2
