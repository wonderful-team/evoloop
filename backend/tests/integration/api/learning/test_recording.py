# ruff: noqa: ARG001
"""Integration tests for the /traces API routes (app/api/routes/learning/recording.py)."""

from __future__ import annotations

import pytest

from app.api.routes.learning.shared import _active_sessions


@pytest.fixture(autouse=True)
def _clean_active_sessions():
    _active_sessions.clear()
    yield
    _active_sessions.clear()


@pytest.fixture(autouse=True)
def _mock_count_persisted(monkeypatch):
    async def _fake_count(session_ids: list[str]) -> dict[str, int]:
        return dict.fromkeys(session_ids, 0)

    monkeypatch.setattr(
        "app.api.routes.learning.recording._count_persisted_events", _fake_count
    )


async def test_start_recording(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.recording.gen_uuid", lambda: "test-uuid-123"
    )
    resp = await client.post(
        "/learning/traces/start",
        json={"thread_id": "t-1", "task_name": "test task"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-uuid-123"
    assert "t-1" in data["message"]


async def test_stop_recording(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.recording.gen_uuid", lambda: "test-uuid-456"
    )
    await client.post("/learning/traces/start", json={"thread_id": "t-1"})
    resp = await client.post("/learning/traces/stop?session_id=test-uuid-456")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-uuid-456"
    assert data["event_count"] == 0


async def test_stop_recording_404(client, monkeypatch):
    resp = await client.post("/learning/traces/stop?session_id=nonexistent")
    assert resp.status_code == 404


async def test_list_sessions(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.recording.gen_uuid", lambda: "sess-aaa"
    )
    await client.post("/learning/traces/start", json={"thread_id": "t-1", "task_name": "task1"})
    resp = await client.get("/learning/traces/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "sess-aaa"


async def test_list_sessions_filter_by_thread(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.recording.gen_uuid",
        lambda: "sess-bbb",
    )
    await client.post("/learning/traces/start", json={"thread_id": "t-2"})
    monkeypatch.setattr(
        "app.api.routes.learning.recording.gen_uuid",
        lambda: "sess-ccc",
    )
    await client.post("/learning/traces/start", json={"thread_id": "t-3"})
    resp = await client.get("/learning/traces/sessions?thread_id=t-2")
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["thread_id"] == "t-2"


async def test_list_sessions_empty(client, monkeypatch):
    resp = await client.get("/learning/traces/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
