"""Recording-session counts + recorder TraceEvent persistence against a real DB.

Covers:
- ``/traces/stop`` and ``/traces/sessions`` event_count derived from persisted
  TraceEvent rows (the in-memory ``_active_sessions`` dict holds no counters).
- ``/mirror/stop`` pops its ``_active_sessions`` entry (leak fix).
- The four recorder endpoints persist rows through the single
  ``_build_trace_event`` construction site with exact field values
  (``state_snapshot`` stored as a dict; legacy double-encoded strings are
  repaired at startup — see ``test_repair_state_snapshot_encoding``).
"""

import json
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes.learning import mirror as mirror_router
from app.api.routes.learning import recording as recording_router
from app.api.routes.learning._shared import _active_sessions
from app.core.learning.schemas import (
    AndroidExtractPointRequest,
    DomEventData,
    DomEventsRequest,
    GlobalEventData,
    GlobalEventsRequest,
    PersistMirrorEventsRequest,
    StartRecordingRequest,
    StopMirrorRequest,
)
from app.infrastructure.database import session_scope
from app.models.learning import TraceEvent


@pytest.fixture
def _clean_sessions():
    _active_sessions.clear()
    yield
    _active_sessions.clear()


async def _insert_traces(session_id: str, n: int) -> None:
    async with session_scope() as db:
        for i in range(n):
            db.add(
                TraceEvent(
                    member_id=0,
                    thread_id="t",
                    session_id=session_id,
                    recording_session_id=session_id,
                    step_number=i,
                    node_name="n",
                    event_type="click",
                    payload={"i": i},
                    source="global",
                )
            )


async def _fetch_rows() -> list[TraceEvent]:
    async with session_scope() as db:
        result = await db.execute(select(TraceEvent))
        return list(result.scalars().all())


# ---------------------------------------------------------------- recording


@pytest.mark.asyncio
async def test_recording_event_count_is_db_derived(_real_db, _clean_sessions):
    started = await recording_router.start_recording(
        StartRecordingRequest(thread_id="t1", task_name="demo")
    )
    sid = started.session_id
    empty = await recording_router.start_recording(
        StartRecordingRequest(thread_id="t1", task_name="empty")
    )
    await _insert_traces(sid, 3)

    listing = await recording_router.list_recording_sessions()
    counts = {s.session_id: s.event_count for s in listing.sessions}
    assert counts == {sid: 3, empty.session_id: 0}

    stopped = await recording_router.stop_recording(session_id=sid)
    assert stopped.event_count == 3
    assert sid not in _active_sessions
    assert empty.session_id in _active_sessions


@pytest.mark.asyncio
async def test_stop_unknown_session_404(_real_db, _clean_sessions):
    with pytest.raises(HTTPException) as exc:
        await recording_router.stop_recording(session_id="nope")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------- mirror


@pytest.mark.asyncio
async def test_stop_mirror_pops_active_session(_real_db, _clean_sessions, monkeypatch):
    _active_sessions["m1"] = {
        "thread_id": "global",
        "task_name": "Android Mirror",
        "started_at": datetime.utcnow(),
    }
    monkeypatch.setattr(
        mirror_router.mirror_manager,
        "stop_session",
        lambda sid: {"video_path": None, "session_id": sid},
    )

    res = await mirror_router.stop_mirror_session(StopMirrorRequest(session_id="m1"))

    assert res.success is True
    assert "m1" not in _active_sessions


@pytest.mark.asyncio
async def test_persist_dom_events_rows(_real_db, _clean_sessions):
    body = DomEventsRequest(
        session_id="s-dom",
        thread_id="t1",
        events=[
            DomEventData(
                timestamp=120.5,
                event_type="click",
                selector="#btn",
                target_text="Go",
                url="https://x.test/a",
                xpath="//button",
            ),
            DomEventData(
                timestamp=130.0,
                event_type="region_extract",
                url="https://x.test/a",
                coordinates={"x": 1, "y": 2, "width": 3, "height": 4},
            ),
        ],
    )

    res = await mirror_router.persist_dom_events(body)

    assert res.count == 2
    rows = await _fetch_rows()
    assert len(rows) == 2
    click, region = rows

    assert click.recording_session_id == "s-dom"
    assert click.thread_id == "t1"
    assert click.member_id == 0
    assert click.source == "dom"
    assert click.node_name == "dom_recorder"
    assert click.action_type == "user_interaction"
    assert click.event_type == "click"
    assert click.target_selector == "#btn"
    assert click.target_text == "Go"
    assert click.app_name == "https://x.test/a"
    assert click.timestamp == 120
    assert click.step_number == 0
    assert click.payload["url"] == "https://x.test/a"
    assert click.payload["platform"] == "web"
    assert click.state_snapshot == {"context": "dom_recorder", "url": "https://x.test/a"}
    assert json.loads(click.action_payload) == click.payload
    assert click.is_human_action is True

    assert region.node_name == "region_marker"
    assert region.action_type == "region_extract"
    assert region.app_name == "screen_region"
    assert region.step_number == 1


@pytest.mark.asyncio
async def test_persist_global_events_rows(_real_db, _clean_sessions):
    body = GlobalEventsRequest(
        session_id="s-g",
        thread_id="t1",
        events=[
            GlobalEventData(
                timestamp=99.0,
                event_type="mouse_click",
                position=(10.0, 20.0),
                window_title="Safari",
                app_name="com.apple.Safari",
                mouse_button="left",
            )
        ],
    )

    res = await mirror_router.persist_global_events(body)

    assert res.count == 1
    (row,) = await _fetch_rows()
    assert row.source == "global"
    assert row.node_name == "com.apple.Safari"
    assert row.app_name == "com.apple.Safari"
    assert row.window_title == "Safari"
    assert row.mouse_x == 10.0
    assert row.mouse_y == 20.0
    assert row.target_selector == "global://screen/10.0/20.0"
    assert row.target_text == "Safari"
    assert row.payload["platform"] == "macos"
    assert row.payload["package_name"] == "com.apple.Safari"
    assert row.payload["mouse_button"] == "left"
    assert row.state_snapshot == {"context": "global_recorder"}
    assert json.loads(row.action_payload) == row.payload
    assert row.is_human_action is True


@pytest.mark.asyncio
async def test_persist_mirror_events_rows(_real_db, _clean_sessions, monkeypatch):
    monkeypatch.setattr(
        mirror_router.mirror_manager,
        "get_session_events",
        lambda sid: [
            {
                "event_type": "tap",
                "timestamp": 500,
                "payload": {"x": 0.1, "y": 0.2, "package_name": "com.app"},
                "target_text": "OK",
            }
        ],
    )

    res = await mirror_router.persist_mirror_events(
        PersistMirrorEventsRequest(session_id="s-m", thread_id="t1")
    )

    assert res.count == 1
    (row,) = await _fetch_rows()
    assert row.source == "mobile"
    assert row.node_name == "android_mirror"
    assert row.app_name == "com.app"
    assert row.target_text == "OK"
    assert row.mouse_x == 0.1
    assert row.mouse_y == 0.2
    assert row.timestamp == 500
    assert row.state_snapshot == {"context": "android_mirror"}
    assert json.loads(row.action_payload) == row.payload
    assert row.is_human_action is True


@pytest.mark.asyncio
async def test_persist_mirror_events_nothing_pending(_real_db, _clean_sessions, monkeypatch):
    monkeypatch.setattr(
        mirror_router.mirror_manager, "get_session_events", lambda sid: []
    )

    res = await mirror_router.persist_mirror_events(
        PersistMirrorEventsRequest(session_id="s-m")
    )

    assert res.count == 0
    assert await _fetch_rows() == []


@pytest.mark.asyncio
async def test_android_extract_point_row(_real_db, _clean_sessions):
    res = await mirror_router.create_android_extract_point(
        AndroidExtractPointRequest(
            session_id="s-a", x=0.25, y=0.5, timestamp_ms=777, note="marker"
        )
    )

    assert res.width == 0.02
    assert res.height == 0.02
    assert res.timestamp_ms == 777
    (row,) = await _fetch_rows()
    assert row.id == res.id
    assert row.thread_id == "global"  # optional thread_id falls back to "global"
    assert row.node_name == "android_region_marker"
    assert row.action_type == "region_extract"
    assert row.event_type == "region_extract"
    assert row.target_selector == "android://screen/0.2500/0.5000"
    assert row.target_text == "marker"
    assert row.source == "android"
    assert row.app_name == "android_mirror"
    assert row.timestamp == 777
    assert row.payload == {
        "coordinates": {"x": 0.25, "y": 0.5, "width": 0.02, "height": 0.02},
        "platform": "android",
        "relative_timestamp_ms": 777,
    }
    assert row.state_snapshot == {"context": "android_region_marker"}
    assert json.loads(row.action_payload) == {
        "x": 0.25,
        "y": 0.5,
        "width": 0.02,
        "height": 0.02,
    }


class TestTraceCallbackHandler:
    """Chain A: agent actions land in trace_events via the wired callback."""

    @pytest.mark.asyncio
    async def test_tool_start_parses_dict_repr_and_persists(self, _real_db):
        from app.core.learning.trace_recorder import TraceCallbackHandler

        handler = TraceCallbackHandler(thread_id="t-chain-a", run_id="r1")
        # Bridge passes str(dict) (single quotes) — must still parse to args
        await handler.on_tool_start(
            serialized={"name": "read_file"},
            input_str="{'path': '/tmp/x', 'limit': 10}",
        )

        async with session_scope() as db:
            rows = (
                await db.execute(
                    select(TraceEvent).where(TraceEvent.thread_id == "t-chain-a")
                )
            ).scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.event_type == "tool_call"
        assert row.node_name == "agent"
        assert row.member_id == 0
        assert row.payload["name"] == "read_file"
        assert row.payload["args"] == {"path": "/tmp/x", "limit": 10}
        assert row.run_id == "r1"

    @pytest.mark.asyncio
    async def test_tool_end_records_tool_name(self, _real_db):
        from app.core.learning.trace_recorder import TraceCallbackHandler

        handler = TraceCallbackHandler(thread_id="t-chain-a2")
        await handler.on_tool_end("file contents", name="read_file")

        async with session_scope() as db:
            rows = (
                await db.execute(
                    select(TraceEvent).where(TraceEvent.thread_id == "t-chain-a2")
                )
            ).scalars().all()

        assert len(rows) == 1
        assert rows[0].event_type == "tool_result"
        assert rows[0].payload["name"] == "read_file"
        assert rows[0].payload["success"] is True
