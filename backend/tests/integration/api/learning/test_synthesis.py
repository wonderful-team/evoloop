# ruff: noqa: ARG001
"""Integration tests for the synthesis API routes (app/api/routes/learning/synthesis.py)."""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    class FakeDb:
        async def flush(self):
            return None

        async def commit(self):
            return None

        async def add(self, *args, **kwargs):
            return None

        async def refresh(self, *args, **kwargs):
            return None

    @asynccontextmanager
    async def _fake_scope():
        yield FakeDb()

    monkeypatch.setattr("app.api.routes.learning.synthesis.session_scope", _fake_scope)


def _fake_event(id=1, payload=None, timestamp=100.0):
    return SimpleNamespace(
        id=id,
        recording_session_id=None,
        timestamp=timestamp,
        target_text="extract point",
        payload=payload or {"coordinates": {"x": 0.5, "y": 0.3, "width": 0.1, "height": 0.1}},
        created_at=datetime.now(timezone.utc),
        action_type="region_extract",
    )


async def _fake_create_from_synthesis(db, **kwargs):
    return SimpleNamespace(id=10, name=kwargs.get("name", "synth-skill"))


async def _fake_create_macro(*args, **kwargs):
    return SimpleNamespace(id=20, macro_script="steps: []")


async def test_synthesize_from_recording(client, monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        monkeypatch.setattr("os.path.exists", lambda p: True)
        synth_result = {
            "skill": {
                "name": "my-skill",
                "description": "desc",
                "namespace": "test",
                "trigger_patterns": ["pattern1"],
                "parameters": [],
                "instructions": "do something",
                "source_session_id": "s1",
                "source_thread_id": "t1",
            },
            "macro_script": "steps: []",
            "metadata": {"frames_analyzed": 5, "events_processed": 10},
        }

        async def _synthesize(recording):
            return synth_result

        monkeypatch.setattr(
            "app.api.routes.learning.synthesis.MultimodalSkillSynthesizer",
            lambda: SimpleNamespace(synthesize=_synthesize),
        )
        monkeypatch.setattr(
            "app.api.routes.learning.synthesis.create_from_synthesis",
            _fake_create_from_synthesis,
        )
        monkeypatch.setattr(
            "app.core.learning.macro.service.MacroService.create_for_skill",
            _fake_create_macro,
        )
        monkeypatch.setattr(
            "app.core.learning.macro.authoring.validate_macro_structure",
            lambda s: (True, None, 2),
        )

        async def _patch_skill(skill, **kw):
            return None

        async def _publish_skill(*args, **kwargs):
            return None

        async def _publish_macro(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.core.learning.skills.lifecycle.patch_skill", _patch_skill
        )
        monkeypatch.setattr(
            "app.api.routes.learning.synthesis.publish_skill_mutated", _publish_skill
        )
        monkeypatch.setattr(
            "app.api.routes.learning.synthesis.publish_macro_mutated", _publish_macro
        )
        monkeypatch.setattr(
            "app.utils.parameters.normalize_parameters", lambda p: p or []
        )
        resp = await client.post(
            "/learning/skills/synthesize-from-recording",
            json={
                "video_path": tmp.name,
                "session_id": "s1",
                "task_description": "open app",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_id"] == 10
        assert data["frames_analyzed"] == 5
    finally:
        os.unlink(tmp.name)


async def test_synthesize_video_not_found(client, monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda p: False)
    resp = await client.post(
        "/learning/skills/synthesize-from-recording",
        json={
            "video_path": "/nonexistent/video.mp4",
            "session_id": "s1",
            "task_description": "test",
        },
    )
    assert resp.status_code == 400


async def test_synthesize_from_recording_error(client, monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda p: True)

    async def _fail(recording):
        raise RuntimeError("LLM failed")

    monkeypatch.setattr(
        "app.api.routes.learning.synthesis.MultimodalSkillSynthesizer",
        lambda: SimpleNamespace(synthesize=_fail),
    )
    resp = await client.post(
        "/learning/skills/synthesize-from-recording",
        json={
            "video_path": "/tmp/fake.mp4",
            "session_id": "s1",
            "task_description": "test",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "LLM failed" in data["error"]


async def test_list_annotations(client, monkeypatch):
    async def _get_by_session(sid, **kw):
        return [_fake_event(1), _fake_event(2)]

    monkeypatch.setattr(
        "app.core.learning.trace.repository.trace_repository.get_by_session",
        _get_by_session,
    )
    resp = await client.get("/learning/recordings/sess-1/annotations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["annotation_type"] == "extract"


async def test_list_annotations_empty(client, monkeypatch):
    async def _get_empty(sid, **kw):
        return []

    monkeypatch.setattr(
        "app.core.learning.trace.repository.trace_repository.get_by_session",
        _get_empty,
    )
    resp = await client.get("/learning/recordings/sess-empty/annotations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_cleanup_recording_session(client, monkeypatch):
    async def _delete(sid, **kw):
        return 5

    monkeypatch.setattr(
        "app.core.learning.trace.repository.trace_repository.delete_by_session",
        _delete,
    )
    resp = await client.delete("/learning/recordings/sess-cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["deleted"]["events"] == 5


async def test_cleanup_recording_with_video(client, monkeypatch):
    async def _delete3(sid, **kw):
        return 3

    monkeypatch.setattr(
        "app.core.learning.trace.repository.trace_repository.delete_by_session",
        _delete3,
    )
    monkeypatch.setattr("os.path.exists", lambda p: True)
    removed = {}
    monkeypatch.setattr("os.remove", lambda p: removed.update({"path": p}))
    resp = await client.delete(
        "/learning/recordings/sess-vid?video_path=/tmp/video.mp4"
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"]["video_file"] is True


async def test_preview_recording_data(client, monkeypatch):
    fake_video_info = SimpleNamespace(
        duration=10.0, width=1920, height=1080, fps=30.0
    )
    fake_events = [SimpleNamespace(action_type="click")]

    class FakeKeyframe:
        def __init__(self, ts, ctx, desc, pri):
            self.timestamp = ts
            self.context = ctx
            self.description = desc
            self.priority = pri

    fake_keyframes = [FakeKeyframe(1.0, "ctx", "desc", "high")]

    async def _get_video_info(path):
        return fake_video_info

    async def _fetch_events(sid):
        return fake_events

    monkeypatch.setattr(
        "app.api.routes.learning.synthesis.MultimodalSkillSynthesizer",
        lambda: SimpleNamespace(
            _get_video_info=_get_video_info, _fetch_events=_fetch_events
        ),
    )
    monkeypatch.setattr(
        "app.infrastructure.vision.video.compressor.KeyframeSelector",
        lambda: SimpleNamespace(
            select_keyframes=lambda events, video_duration: fake_keyframes
        ),
    )
    resp = await client.get(
        "/learning/skills/synthesize-from-recording/preview?session_id=s1&video_path=/tmp/v.mp4"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["video_info"]["duration"] == 10.0
    assert data["events"]["total"] == 1
