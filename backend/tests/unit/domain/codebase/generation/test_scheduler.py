"""Unit tests for app.domain.codebase.generation.scheduler."""

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.codebase.generation.scheduler import (
    GENERATION_ITEMS,
    GenerationScheduler,
)


@pytest.fixture
async def scheduler(tmp_path):
    s = GenerationScheduler(base_dir=tmp_path)
    yield s
    await s.close()


class TestGenerationScheduler:
    async def test_dispatch_known_items(self, scheduler):
        with (
            patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()),
        ):
            result = await scheduler.dispatch(1, ["wiki", "appmap"])
        assert result["project_id"] == 1
        assert "wiki" in result["dispatched"]
        assert "appmap" in result["dispatched"]
        assert result["items"]["wiki"]["status"] == "running"

    async def test_dispatch_unknown_item_ignored(self, scheduler):
        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            result = await scheduler.dispatch(1, ["wiki", "unknown"])
        assert result["dispatched"] == ["wiki"]
        assert "unknown" not in result["items"]

    async def test_list_status_returns_all_items(self, scheduler):
        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            await scheduler.dispatch(1, ["wiki"])
        records = await scheduler.list_status(1)
        items = {r["item"]: r for r in records}
        assert items.keys() == GENERATION_ITEMS
        # wiki was dispatched so its status is running; others remain pending.
        assert items["wiki"]["status"] in ("running", "pending")
        assert items["appmap"]["status"] == "pending"
        assert items["summary"]["status"] == "pending"

    async def test_retry_failed_item(self, scheduler):
        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            # Manually set a failed record.
            store = scheduler._load(1)
            record = scheduler._ensure_record(store, "wiki")
            scheduler._update_record(record, "failed", error="timeout")
            scheduler._save(store)

            result = await scheduler.retry(1, "wiki")
        assert result["status"] == "running"

    async def test_retry_unknown_item_returns_error(self, scheduler):
        result = await scheduler.retry(1, "unknown")
        assert "error" in result

    async def test_already_running_item_not_re_dispatched(self, scheduler):
        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            result = await scheduler.dispatch(1, ["wiki"])
        assert result["items"]["wiki"]["status"] == "running"

        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            second = await scheduler.dispatch(1, ["wiki"])
        assert second["dispatched"] == []

    async def test_content_retrieved_after_completion(self, scheduler, tmp_path):
        """Verify status tracking after a background item completes."""
        with (
            patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()),
        ):
            result = await scheduler.dispatch(1, ["wiki"])
            assert result["items"]["wiki"]["status"] == "running"

        # Manually simulate completion (as _run_item would do).
        async with scheduler._lock(1):
            store = scheduler._load(1)
            record = scheduler._ensure_record(store, "wiki")
            record.thread_id = "test-thread"
            record.content = "Generated via Agent (thread: test-thread)."
            scheduler._update_record(record, "completed")
            scheduler._save(store)

        content = await scheduler.get_content(1, "wiki")
        assert content["item"] == "wiki"
        assert content["content_type"] == "markdown"
        assert "test-thread" in (content["content"] or "")

    async def test_status_persistence_across_scheduler_instances(self, scheduler, tmp_path):
        """Verify the JSON file persists status across instances."""
        with patch("app.domain.codebase.generation.scheduler.publish_generation_status_changed", AsyncMock()):
            await scheduler.dispatch(1, ["appmap"])
        await scheduler.close()

        s2 = GenerationScheduler(base_dir=tmp_path)
        records = await s2.list_status(1)
        items = {r["item"]: r for r in records}
        assert items["appmap"]["status"] == "running"
        await s2.close()
