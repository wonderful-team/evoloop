"""Coverage for app.core.learning.trace.repository (trace_events access)."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import delete

from app.core.learning.trace.repository import trace_repository
from app.models.learning import TraceEvent


@pytest.fixture(autouse=True)
def _clean_events(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(TraceEvent))

    asyncio.run(_clean())


@pytest.fixture(autouse=True)
def repo_scope(test_session_scope, monkeypatch):
    from app.core.learning.trace import repository as repo_module

    monkeypatch.setattr(repo_module, "session_scope", test_session_scope)


class TestBuildEvent:
    def test_defaults_action_payload_to_payload(self):
        event = trace_repository.build_event(
            member_id=5,
            session_id="s1",
            thread_id="global",
            step_number=1,
            node_name="node",
            action_type="user_interaction",
            timestamp=100,
            event_type="click",
            source="mobile",
            app_name="com.app",
            payload={"x": 1},
            state_context={"context": "android_mirror"},
        )
        assert event.member_id == 5
        assert event.recording_session_id == "s1"
        assert event.is_human_action is True
        assert event.action_payload == json.dumps({"x": 1})
        assert event.state_snapshot == {"context": "android_mirror"}

    def test_custom_action_payload_and_human_flag(self):
        event = trace_repository.build_event(
            member_id=0,
            session_id="s",
            thread_id="t",
            step_number=0,
            node_name="n",
            action_type="region_extract",
            timestamp=1,
            event_type="region_extract",
            source="android",
            app_name=None,
            payload={},
            state_context={},
            action_payload={"w": 2},
            is_human_action=False,
        )
        assert event.action_payload == json.dumps({"w": 2})
        assert event.is_human_action is False


@pytest.mark.asyncio
class TestPersistence:
    def _event(self, **kw) -> TraceEvent:
        defaults = {
            "member_id": 0,
            "session_id": "s1",
            "thread_id": "global",
            "step_number": 0,
            "node_name": "node",
            "action_type": "user_interaction",
            "timestamp": 1,
            "event_type": "click",
            "source": "mobile",
            "app_name": None,
            "payload": {},
            "state_context": {},
        }
        defaults.update(kw)
        return trace_repository.build_event(**defaults)

    async def test_add_and_add_all(self, test_session_scope):
        async with test_session_scope() as db:
            e1 = await trace_repository.add(db, self._event(step_number=1))
            await trace_repository.add_all(
                db, [self._event(step_number=2, session_id="s2"), self._event(step_number=3, session_id="s2")]
            )
            assert e1.id is not None

    async def test_count_by_session_with_and_without_member(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(member_id=0, session_id="s1", step_number=1),
                    self._event(member_id=7, session_id="s1", step_number=2),
                    self._event(member_id=7, session_id="s2", step_number=3),
                ],
            )
        assert await trace_repository.count_by_session("s1") == 2
        assert await trace_repository.count_by_session("s1", member_id=7) == 1
        assert await trace_repository.count_by_session("nope") == 0

    async def test_count_by_sessions(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(session_id="s1", step_number=1),
                    self._event(session_id="s1", step_number=2),
                    self._event(session_id="s2", step_number=3),
                ],
            )
        counts = await trace_repository.count_by_sessions(["s1", "s2"])
        assert counts == {"s1": 2, "s2": 1}
        assert await trace_repository.count_by_sessions([]) == {}

    async def test_get_by_session_filter_and_order(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(session_id="s1", step_number=1, timestamp=3, action_type="region_extract"),
                    self._event(session_id="s1", step_number=2, timestamp=1, action_type="user_interaction"),
                    self._event(member_id=9, session_id="s1", step_number=3, timestamp=2),
                ],
            )
        events = await trace_repository.get_by_session("s1", member_id=0)
        assert [e.timestamp for e in events] == [1, 3]
        extract = await trace_repository.get_by_session("s1", action_type="region_extract")
        assert len(extract) == 1 and extract[0].action_type == "region_extract"

    async def test_get_by_thread_orders_by_step(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(thread_id="t1", step_number=3),
                    self._event(thread_id="t1", step_number=1),
                    self._event(thread_id="t2", step_number=9),
                ],
            )
        events = await trace_repository.get_by_thread("t1")
        assert [e.step_number for e in events] == [1, 3]

    async def test_get_by_session_match_session_id(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(session_id="s1", step_number=1),
                    TraceEvent(
                        thread_id="t",
                        step_number=2,
                        node_name="n",
                        event_type="click",
                        payload={},
                        session_id="legacy",
                        recording_session_id="s1",
                        timestamp=2,
                    ),
                ],
            )
        # default matches recording_session_id only
        assert len(await trace_repository.get_by_session("s1")) == 2
        # match_session_id matches either column (adds the legacy one)
        assert len(await trace_repository.get_by_session("s1", match_session_id=True)) == 2

    async def test_delete_by_session(self, test_session_scope):
        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    self._event(member_id=7, session_id="s1", step_number=1),
                    self._event(member_id=7, session_id="s1", step_number=2),
                    self._event(member_id=0, session_id="s1", step_number=3),
                ],
            )
        deleted = await trace_repository.delete_by_session("s1", member_id=7)
        assert deleted == 2
        assert await trace_repository.count_by_session("s1") == 1

    async def test_delete_by_thread(self, test_session_scope):
        def _raw(**kw) -> TraceEvent:
            defaults = {
                "thread_id": "t1",
                "step_number": 0,
                "node_name": "n",
                "event_type": "click",
                "payload": {},
            }
            defaults.update(kw)
            return TraceEvent(**defaults)

        async with test_session_scope() as db:
            await trace_repository.add_all(
                db,
                [
                    _raw(step_number=1, message_id="m1"),
                    _raw(step_number=2, message_id="m2"),
                    _raw(thread_id="t2", step_number=3),
                ],
            )
        # narrowed by message ids
        assert await trace_repository.delete_by_thread("t1", message_ids=["m1"]) == 1
        # whole thread delete of the remainder
        assert await trace_repository.delete_by_thread("t1") == 1
        assert await trace_repository.delete_by_thread("t2") == 1

