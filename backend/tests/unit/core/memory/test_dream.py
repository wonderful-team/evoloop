"""Deep Dream distillation tests: replay, distiller, scheduler."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.memory.dream import (
    DeepDreamDistiller,
    DreamScheduler,
    EpisodeReplay,
    DreamInsight,
    DreamResult,
)
from app.core.memory.dream.scheduler import trigger_dream
from app.core.memory.models import MemoryEntry, MemoryType, MemoryTier


# =============================================================================
# EpisodeReplay tests
# =============================================================================

class TestEpisodeReplay:
    """EpisodeReplay — loading and formatting episodes."""

    @pytest.mark.asyncio
    async def test_load_recent_episodes_returns_episodes(self):
        manager = MagicMock()
        ep1 = MemoryEntry(
            id="ep_1", type=MemoryType.EPISODE, title="Episode: fix bug",
            content="Goal: fix bug\nOutcome: success", description="success",
            updated_at=datetime.now(),
        )
        manager.search_memories = AsyncMock(return_value=[ep1])

        replay = EpisodeReplay(manager)
        episodes = await replay.load_recent_episodes(days_back=7, limit=10)

        assert len(episodes) == 1
        assert episodes[0]["goal"] == "fix bug"
        assert "success" in episodes[0]["result"]

    @pytest.mark.asyncio
    async def test_load_filters_old_episodes(self):
        manager = MagicMock()
        old_ep = MemoryEntry(
            id="ep_old", type=MemoryType.EPISODE, title="Episode: old",
            content="old", updated_at=datetime.now() - timedelta(days=30),
        )
        recent_ep = MemoryEntry(
            id="ep_new", type=MemoryType.EPISODE, title="Episode: new",
            content="new", updated_at=datetime.now(),
        )
        manager.search_memories = AsyncMock(return_value=[old_ep, recent_ep])

        replay = EpisodeReplay(manager)
        episodes = await replay.load_recent_episodes(days_back=7)

        assert len(episodes) == 1
        assert episodes[0]["id"] == "ep_new"

    @pytest.mark.asyncio
    async def test_load_handles_empty_result(self):
        manager = MagicMock()
        manager.search_memories = AsyncMock(return_value=[])

        replay = EpisodeReplay(manager)
        episodes = await replay.load_recent_episodes()

        assert episodes == []

    @pytest.mark.asyncio
    async def test_load_handles_exception(self):
        manager = MagicMock()
        manager.search_memories = AsyncMock(side_effect=RuntimeError("DB error"))

        replay = EpisodeReplay(manager)
        episodes = await replay.load_recent_episodes()

        assert episodes == []

    def test_format_for_distillation_renders_episodes(self):
        replay = EpisodeReplay(MagicMock())
        episodes = [
            {"goal": "fix bug", "result": "success", "description": "ok", "id": "1"},
            {"goal": "add feature", "result": "done", "description": "done", "id": "2"},
        ]
        text = replay.format_for_distillation(episodes)

        assert "## Episode 1" in text
        assert "## Episode 2" in text
        assert "fix bug" in text
        assert "add feature" in text

    def test_format_empty_episodes(self):
        replay = EpisodeReplay(MagicMock())
        text = replay.format_for_distillation([])

        assert "no episodes" in text


# =============================================================================
# DeepDreamDistiller tests
# =============================================================================

class TestDeepDreamDistiller:
    """DeepDreamDistiller — LLM distillation and insight storage."""

    @pytest.mark.asyncio
    async def test_dream_skips_with_few_episodes(self):
        manager = MagicMock()
        manager.search_memories = AsyncMock(return_value=[])
        distiller = DeepDreamDistiller(manager)

        result = await distiller.dream()

        assert result.episodes_replayed == 0
        assert len(result.insights_generated) == 0
        assert result.succeeded

    @pytest.mark.asyncio
    async def test_dream_distills_and_stores_insights(self):
        # Clean up any leftover hash file from other tests/runs
        from pathlib import Path
        from app.core.config import settings
        hash_file_path = Path(settings.APP_DATA_DIR) / "memory" / ".last_dream_hash_global"
        if hash_file_path.exists():
            try:
                hash_file_path.unlink()
            except Exception:
                pass

        ep = MemoryEntry(
            id="ep_1", type=MemoryType.EPISODE, title="Episode: test",
            content="Goal: test\nOutcome: passed", description="passed",
            updated_at=datetime.now(),
        )
        ep2 = MemoryEntry(
            id="ep_2", type=MemoryType.EPISODE, title="Episode: test2",
            content="Goal: test2\nOutcome: passed2", description="passed2",
            updated_at=datetime.now(),
        )
        manager = MagicMock()
        manager.search_memories = AsyncMock(return_value=[ep, ep2])
        manager.get_memory = AsyncMock(return_value=None)
        manager.save_memory = AsyncMock()
        manager._two_tier = MagicMock()
        manager._two_tier.regenerate_memory_md = AsyncMock()

        distiller = DeepDreamDistiller(manager)

        llm_response = MagicMock()
        llm_response.content = '[{"title": "Pattern X", "content": "Use X for Y", "category": "pattern", "utility_score": 0.9, "related_goals": ["test"]}]'

        with patch("app.infrastructure.llm.InternalLLMService.invoke", AsyncMock(return_value=llm_response)):
            with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="test-model"):
                with patch("app.core.memory.dream.distiller.render_template", return_value="prompt text"):
                    result = await distiller.dream()

        assert result.episodes_replayed == 2
        assert len(result.insights_generated) == 1
        assert len(result.insight_ids) == 1
        assert result.insights_generated[0].title == "Pattern X"
        assert result.insights_generated[0].category == "pattern"
        manager.save_memory.assert_awaited_once()

    def test_parse_insights_valid_json(self):
        distiller = DeepDreamDistiller(MagicMock())
        content = 'Some text [{"title": "Insight 1", "content": "Content 1", "category": "gotcha", "utility_score": 0.7}] more text'
        insights = distiller._parse_insights(content)

        assert len(insights) == 1
        assert insights[0].title == "Insight 1"
        assert insights[0].category == "gotcha"
        assert insights[0].utility_score == 0.7

    def test_parse_insights_no_json(self):
        distiller = DeepDreamDistiller(MagicMock())
        insights = distiller._parse_insights("no json here")
        assert insights == []

    def test_parse_insights_malformed_json(self):
        distiller = DeepDreamDistiller(MagicMock())
        insights = distiller._parse_insights('[{"title": "bad"')
        assert insights == []

    @pytest.mark.asyncio
    async def test_store_insight_dedup(self):
        manager = MagicMock()
        existing = MemoryEntry(id="dream_abc", type=MemoryType.CONCEPT, title="T", content="C")
        manager.get_memory = AsyncMock(return_value=existing)
        manager.save_memory = AsyncMock()

        distiller = DeepDreamDistiller(manager)
        insight = DreamInsight(title="Test", content="content", category="pattern")
        entry_id = await distiller._store_insight(insight, project_id=None)

        assert entry_id is None
        manager.save_memory.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_store_insight_creates_entry(self):
        manager = MagicMock()
        manager.get_memory = AsyncMock(return_value=None)
        manager.save_memory = AsyncMock()

        distiller = DeepDreamDistiller(manager)
        insight = DreamInsight(title="Test", content="content", category="pattern", utility_score=0.9)
        entry_id = await distiller._store_insight(insight, project_id=1)

        assert entry_id is not None
        assert entry_id.startswith("dream_")
        manager.save_memory.assert_awaited_once()
        saved_entry = manager.save_memory.call_args[0][0]
        assert saved_entry.type == MemoryType.CONCEPT
        assert saved_entry.tier == MemoryTier.STRATEGIC
        assert saved_entry.source == "deep_dream"
        assert "pattern" in saved_entry.tags

    @pytest.mark.asyncio
    async def test_dream_skips_when_hash_matches(self, monkeypatch, tmp_path):
        ep = MemoryEntry(
            id="ep_1", type=MemoryType.EPISODE, title="Episode: test",
            content="Goal: test\nOutcome: passed", description="passed",
            updated_at=datetime.now(),
        )
        ep2 = MemoryEntry(
            id="ep_2", type=MemoryType.EPISODE, title="Episode: test2",
            content="Goal: test2\nOutcome: passed2", description="passed2",
            updated_at=datetime.now(),
        )
        manager = MagicMock()
        manager.search_memories = AsyncMock(return_value=[ep, ep2])
        manager.get_memory = AsyncMock(return_value=None)
        manager.save_memory = AsyncMock()
        manager._two_tier = MagicMock()
        manager._two_tier.regenerate_memory_md = AsyncMock()

        # Patch APP_DATA_DIR to tmp_path so it writes/reads the hash file there
        from app.core.config import settings
        monkeypatch.setattr(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path))

        distiller = DeepDreamDistiller(manager)

        llm_response = MagicMock()
        llm_response.content = '[{"title": "Pattern X", "content": "Use X for Y", "category": "pattern", "utility_score": 0.9, "related_goals": ["test"]}]'

        # First run (should invoke LLM)
        with patch("app.infrastructure.llm.InternalLLMService.invoke", AsyncMock(return_value=llm_response)) as mock_invoke:
            with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="test-model"):
                with patch("app.core.memory.dream.distiller.render_template", return_value="prompt text"):
                    result1 = await distiller.dream()
                    assert len(result1.insight_ids) == 1
                    assert mock_invoke.call_count == 1

        # Second run (should skip LLM call)
        with patch("app.infrastructure.llm.InternalLLMService.invoke", AsyncMock(return_value=llm_response)) as mock_invoke2:
            with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="test-model"):
                with patch("app.core.memory.dream.distiller.render_template", return_value="prompt text"):
                    result2 = await distiller.dream()
                    assert len(result2.insight_ids) == 0
                    assert mock_invoke2.call_count == 0


# =============================================================================
# DreamScheduler tests
# =============================================================================

class TestDreamScheduler:
    """DreamScheduler — scheduling and trigger logic."""

    @pytest.mark.asyncio
    async def test_should_run_first_time(self):
        scheduler = DreamScheduler(MagicMock())
        with patch.object(scheduler, "_get_last_run_time", return_value=None):
            assert await scheduler.should_run() is True

    @pytest.mark.asyncio
    async def test_should_run_recent_skip(self):
        scheduler = DreamScheduler(MagicMock())
        with patch.object(scheduler, "_get_last_run_time", return_value=datetime.now()):
            assert await scheduler.should_run() is False

    @pytest.mark.asyncio
    async def test_should_run_old_trigger(self):
        scheduler = DreamScheduler(MagicMock())
        with patch.object(scheduler, "_get_last_run_time", return_value=datetime.now() - timedelta(hours=48)):
            assert await scheduler.should_run() is True

    @pytest.mark.asyncio
    async def test_run_skips_when_recent(self):
        scheduler = DreamScheduler(MagicMock())
        with patch.object(scheduler, "_get_last_run_time", return_value=datetime.now()):
            result = await scheduler.run()
            assert result is None

    @pytest.mark.asyncio
    async def test_run_executes_dream(self):
        manager = MagicMock()
        scheduler = DreamScheduler(manager)

        mock_result = DreamResult(
            started_at=datetime.now(),
            finished_at=datetime.now(),
            episodes_replayed=3,
            insight_ids=["dream_1"],
        )
        mock_result.insights_generated = [DreamInsight(title="T", content="C", category="pattern")]

        with patch.object(scheduler, "_get_last_run_time", return_value=None):
            with patch.object(scheduler, "_save_record"):
                with patch("app.core.memory.dream.scheduler.DeepDreamDistiller") as MockDistiller:
                    instance = MockDistiller.return_value
                    instance.dream = AsyncMock(return_value=mock_result)
                    result = await scheduler.run()

        assert result is not None
        assert result.episodes_count == 3
        assert result.insights_count == 1

    def test_trigger_dream_sync(self):
        with patch("app.core.memory.dream.scheduler.DreamScheduler") as MockSched:
            instance = MockSched.return_value
            instance.run = AsyncMock(return_value=None)
            result = trigger_dream()
            # Returns None when dream is skipped
            assert result is None
