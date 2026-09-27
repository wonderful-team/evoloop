"""Coverage for TraceRecorder / TraceCallbackHandler / sync_thread_to_graph."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

from app.core.learning.trace import recorder as recorder_module
from app.core.learning.trace.recorder import (
    TraceRecorder,
    get_recorder,
    sync_thread_to_graph,
)
from app.models.learning import TraceEvent


@pytest.fixture(autouse=True)
def _clean(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(TraceEvent))

    asyncio.run(_clean())


@pytest.fixture
def recorder_scope(test_session_scope, monkeypatch):
    from app.core.learning.trace import repository as repo_module

    monkeypatch.setattr(repo_module, "session_scope", test_session_scope)


@pytest.mark.asyncio
class TestTraceRecorder:
    def test_get_recorder_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            recorder_module, "settings", SimpleNamespace(BROWSER_ARTIFACTS_DIR=str(tmp_path))
        )
        rec = get_recorder("s1")
        assert rec is get_recorder("s1")
        assert rec.session_id == "s1"

    async def test_record_action_with_screenshot_and_stop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            recorder_module, "settings", SimpleNamespace(BROWSER_ARTIFACTS_DIR=str(tmp_path))
        )
        rec = TraceRecorder("s2")
        rec.start()
        await rec.record_action(
            "click",
            "mobile",
            {"x": 1},
            context={"screen": "home"},
            screenshot_data=b"png-data",
        )
        rec.stop()
        assert rec.is_recording is False
        assert len(rec.traces) == 1
        trace_file = tmp_path / "traces" / "s2" / "trace.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text(encoding="utf-8"))
        assert data["step_count"] == 1
        assert data["traces"][0]["action_type"] == "click"
        # a screenshot PNG is persisted alongside the trace
        shots = list((tmp_path / "traces" / "s2").glob("step_*.png"))
        assert len(shots) == 1

    async def test_record_ignored_when_not_recording(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            recorder_module, "settings", SimpleNamespace(BROWSER_ARTIFACTS_DIR=str(tmp_path))
        )
        rec = TraceRecorder("s3")
        await rec.record_action("click", "mobile", {})
        assert rec.traces == []


@pytest.mark.asyncio
class TestSyncThreadToGraph:
    async def test_no_events_skips(self, recorder_scope, monkeypatch):
        initialized = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "app.core.memory.lifespan.MemoryLifespanManager.is_initialized",
            staticmethod(initialized),
        )
        await sync_thread_to_graph(thread_id="empty", project_id=1, goal="g")
        initialized.assert_not_awaited()

    async def test_records_episode(self, recorder_scope, test_session_scope, monkeypatch):
        async with test_session_scope() as db:
            db.add(
                TraceEvent(
                    thread_id="t1",
                    step_number=1,
                    node_name="n",
                    event_type="tool_call",
                    payload={},
                    source="agent",
                )
            )
            await db.flush()

        record_episode = AsyncMock(return_value="ep1")
        container = SimpleNamespace(memory_manager=SimpleNamespace(record_episode=record_episode))
        monkeypatch.setattr(
            "app.core.memory.lifespan.MemoryLifespanManager.is_initialized",
            staticmethod(lambda: True),
        )
        monkeypatch.setattr(
            "app.core.memory.lifespan.MemoryLifespanManager.get_container",
            staticmethod(lambda: container),
        )

        await sync_thread_to_graph(
            thread_id="t1", project_id=1, goal="goal", result_summary="done"
        )
        record_episode.assert_awaited_once()
