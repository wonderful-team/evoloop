# ruff: noqa: ARG001
"""Integration tests for the /mirror API routes (app/api/routes/learning/mirror.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes.learning.shared import _active_sessions


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    async def _flush():
        return None

    async def _refresh(obj):
        return None

    class _FakeDb:
        db = "fake"

        async def flush(self):
            return None

        async def refresh(self, obj):
            return None

    @asynccontextmanager
    async def _fake_scope():
        yield _FakeDb()

    monkeypatch.setattr("app.api.routes.learning.mirror.session_scope", _fake_scope)


@pytest.fixture(autouse=True)
def _clean_active_sessions():
    _active_sessions.clear()
    yield
    _active_sessions.clear()


async def test_list_mirror_devices(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.adb_driver.list_devices",
        lambda: [{"id": "emulator-5554", "name": "Pixel 6"}],
    )
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = await client.get("/learning/mirror/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["devices"]) == 1
    assert data["scrcpy_available"] is False


async def test_start_mirror_session(client, monkeypatch):
    async def _create(did, record_video=False):
        return SimpleNamespace(
            is_active=True, session_id="sess-123", device_id=did, error=None
        )

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.create_session", _create
    )
    resp = await client.post(
        "/learning/mirror/start", json={"device_id": "emulator-5554"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-123"
    assert data["device_id"] == "emulator-5554"
    assert "sess-123" in _active_sessions


async def test_start_mirror_session_failure(client, monkeypatch):
    async def _create(did, record_video=False):
        return SimpleNamespace(
            is_active=False, session_id=None, device_id=did, error="scrcpy not found"
        )

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.create_session", _create
    )
    resp = await client.post(
        "/learning/mirror/start", json={"device_id": "bad-device"}
    )
    assert resp.status_code == 500


async def test_start_recording(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.start_recording",
        lambda sid: True,
    )
    resp = await client.post(
        "/learning/mirror/start-recording", json={"session_id": "sess-aaa"}
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-aaa"


async def test_start_recording_failure(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.start_recording",
        lambda sid: False,
    )
    resp = await client.post(
        "/learning/mirror/start-recording", json={"session_id": "bad-sess"}
    )
    assert resp.status_code == 400


async def test_stop_mirror_session(client, monkeypatch):
    _active_sessions["sess-xyz"] = {
        "thread_id": "global",
        "task_name": "Mirror",
        "started_at": datetime.now(timezone.utc),
    }
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.stop_session",
        lambda sid: {"video_path": "/tmp/v.mp4", "session_id": sid},
    )
    async def _count(sid, **kw):
        return 42

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.count_by_session", _count
    )
    resp = await client.post("/learning/mirror/stop", json={"session_id": "sess-xyz"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_count"] == 42
    assert data["video_path"] == "/tmp/v.mp4"


async def test_stop_mirror_session_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.stop_session",
        lambda sid: None,
    )
    resp = await client.post("/learning/mirror/stop", json={"session_id": "nope"})
    assert resp.status_code == 404


async def test_device_resolution(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.adb_driver.get_screen_size",
        lambda did: (720, 1280),
    )
    resp = await client.get("/learning/mirror/device/emulator-5554/resolution")
    assert resp.status_code == 200
    data = resp.json()
    assert data["width"] == 720
    assert data["height"] == 1280


async def test_device_resolution_fallback(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.adb_driver.get_screen_size",
        lambda did: None,
    )
    resp = await client.get("/learning/mirror/device/emulator-5554/resolution")
    assert resp.status_code == 200
    assert resp.json()["width"] == 1080


async def test_persist_mirror_events_empty(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.get_session_events",
        lambda sid: [],
    )
    resp = await client.post(
        "/learning/mirror/events", json={"session_id": "sess-empty"}
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_persist_mirror_events_already_persisted(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.mirror_manager.get_session_events",
        lambda sid: [{"event_type": "click"}],
    )
    async def _count(sid, **kw):
        return 10

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.count_by_session", _count
    )
    resp = await client.post(
        "/learning/mirror/events", json={"session_id": "sess-already"}
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 10


async def test_persist_global_events_empty(client, monkeypatch):
    resp = await client.post(
        "/learning/global/events",
        json={"session_id": "s", "thread_id": "t", "events": []},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_persist_global_events(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.build_event",
        lambda **kw: SimpleNamespace(id=1),
    )
    async def _add(db, ev):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.add", _add
    )
    events = [
        {
            "timestamp": 1000.0,
            "event_type": "mouse_click",
            "key": None,
            "mouse_button": "left",
            "position": [100.0, 200.0],
            "window_title": "Test",
            "app_name": "com.test",
            "process_id": 1,
        }
    ]
    resp = await client.post(
        "/learning/global/events",
        json={"session_id": "s", "thread_id": "t", "events": events},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


async def test_persist_dom_events_empty(client, monkeypatch):
    resp = await client.post(
        "/learning/dom/events",
        json={"session_id": "s", "thread_id": "t", "events": []},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_persist_dom_events(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.build_event",
        lambda **kw: SimpleNamespace(id=1),
    )
    async def _add(db, ev):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.add", _add
    )
    events = [
        {
            "timestamp": 500.0,
            "event_type": "click",
            "selector": "#btn",
            "target_text": "Submit",
            "value": None,
            "url": "https://example.com",
            "xpath": None,
            "coordinates": None,
        }
    ]
    resp = await client.post(
        "/learning/dom/events",
        json={"session_id": "s", "thread_id": "t", "events": events},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


async def test_upload_screenshot(client, monkeypatch):

    monkeypatch.setattr(
        "app.infrastructure.vision.storage.screenshot_storage.save_screenshot",
        lambda **kw: "/tmp/screenshots/test.png",
    )
    resp = await client.post(
        "/learning/assets/upload-screenshot",
        files={"file": ("test.png", b"\x89PNG", "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "path" in data


async def test_create_android_extract_point(client, monkeypatch):
    fake_event = SimpleNamespace(
        id=42,
        created_at=datetime.now(timezone.utc),
        flush=lambda: None,
        refresh=lambda: None,
    )

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.build_event",
        lambda **kw: fake_event,
    )
    async def _add(db, ev):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.add", _add
    )
    resp = await client.post(
        "/learning/mirror/extract-point",
        json={
            "session_id": "s",
            "x": 0.5,
            "y": 0.3,
            "width": 0.1,
            "height": 0.1,
            "note": "test point",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["x"] == 0.5
    assert data["note"] == "test point"


async def test_list_extract_points(client, monkeypatch):
    async def _get_by_session(sid, **kw):
        return []

    monkeypatch.setattr(
        "app.api.routes.learning.mirror.trace_repository.get_by_session",
        _get_by_session,
    )
    resp = await client.get("/learning/mirror/sess-abc/extract-points")
    assert resp.status_code == 200
    assert resp.json() == []
