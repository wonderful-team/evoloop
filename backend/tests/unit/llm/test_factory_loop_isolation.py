"""
Verify that LLMFactory._instance_cache isolates cached instances per event loop.
This prevents the "client has been closed" error when Huey tasks create new
event loops via asyncio.run() while reusing globally cached LLM instances.
"""

import asyncio
import weakref
from unittest.mock import MagicMock, patch

import pytest


class TestLLMFactoryLoopIsolation:
    """Test that LLMFactory cache isolates instances per event loop."""

    @pytest.fixture(autouse=True)
    def clear_factory_cache(self):
        """Clear factory cache before each test."""
        from app.infrastructure.llm.factory import LLMFactory
        LLMFactory.clear_cache()
        yield
        LLMFactory.clear_cache()

    def test_instance_cache_is_weak_key_dictionary(self):
        """_instance_cache must be a WeakKeyDictionary keyed by event loop."""
        from app.infrastructure.llm.factory import LLMFactory

        cache = LLMFactory._instance_cache
        assert isinstance(cache, weakref.WeakKeyDictionary)

    def test_cache_is_empty_after_clear(self):
        """clear_cache() empties all per-loop caches."""
        from app.infrastructure.llm.factory import LLMFactory

        LLMFactory._instance_cache[asyncio.new_event_loop()] = {"k": "v"}
        LLMFactory.clear_cache()
        assert len(LLMFactory._instance_cache) == 0

    @pytest.mark.asyncio
    async def test_same_loop_same_cache(self):
        """Same event loop → same cache bucket → cache hit."""
        from app.infrastructure.llm.factory import LLMFactory

        loop = asyncio.get_running_loop()

        # Manually inject a mock instance into the current loop's cache
        mock_llm = MagicMock()
        LLMFactory._instance_cache[loop] = {"test-key": mock_llm}

        # Verify we can read it back
        loop_cache = LLMFactory._instance_cache.get(loop)
        assert loop_cache is not None
        assert "test-key" in loop_cache
        assert loop_cache["test-key"] is mock_llm

    def test_different_loops_different_caches(self):
        """Different event loops → isolated cache buckets."""
        from app.infrastructure.llm.factory import LLMFactory

        loop_a = asyncio.new_event_loop()
        loop_b = asyncio.new_event_loop()

        mock_llm_a = MagicMock()
        mock_llm_b = MagicMock()

        LLMFactory._instance_cache[loop_a] = {"key": mock_llm_a}
        LLMFactory._instance_cache[loop_b] = {"key": mock_llm_b}

        # Each loop sees its own instance
        assert LLMFactory._instance_cache[loop_a]["key"] is mock_llm_a
        assert LLMFactory._instance_cache[loop_b]["key"] is mock_llm_b

        # They are not the same object
        assert mock_llm_a is not mock_llm_b

    def test_loop_gc_removes_cache_entry(self):
        """When an event loop is garbage collected, its cache entry is auto-removed."""
        from app.infrastructure.llm.factory import LLMFactory

        # Create a loop in a scoped function so it can be GC'd
        def _create_loop_and_cache():
            loop = asyncio.new_event_loop()
            LLMFactory._instance_cache[loop] = {"key": MagicMock()}
            return loop

        loop = _create_loop_and_cache()
        assert len(LLMFactory._instance_cache) == 1

        # Drop the only strong reference; WeakKeyDictionary should auto-remove
        del loop

        # Force garbage collection
        import gc
        gc.collect()

        assert len(LLMFactory._instance_cache) == 0

    @pytest.mark.asyncio
    async def test_create_llm_uses_current_loop(self):
        """create_llm reads/writes the cache keyed by the running event loop."""
        from app.infrastructure.llm.factory import LLMFactory

        loop = asyncio.get_running_loop()

        # Mock _create_platform_llm to avoid real LLM initialization
        fake_instance = {"mock": "llm"}
        with patch.object(LLMFactory, "_create_platform_llm", return_value=fake_instance):
            from app.infrastructure.schemas import LLMConfig
            config = LLMConfig(model_name="gpt-4")

            instance = await LLMFactory.create_llm(config)

        # The instance should be stored under the current loop
        assert loop in LLMFactory._instance_cache
        loop_cache = LLMFactory._instance_cache[loop]
        assert len(loop_cache) == 1
        assert list(loop_cache.values())[0] is instance

    @pytest.mark.asyncio
    async def test_create_llm_cache_hit_same_loop(self):
        """Calling create_llm twice with same config on same loop → cache hit."""
        from app.infrastructure.llm.factory import LLMFactory

        call_count = 0
        fake_instance = {"mock": "llm"}

        async def _mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return fake_instance

        with patch.object(LLMFactory, "_create_platform_llm", side_effect=_mock_create):
            from app.infrastructure.schemas import LLMConfig
            config = LLMConfig(model_name="gpt-4")

            instance1 = await LLMFactory.create_llm(config)
            instance2 = await LLMFactory.create_llm(config)

        assert instance1 is instance2, "Same loop should return cached instance"
        assert call_count == 1, "Only one creation call expected"

    def test_create_llm_cache_miss_different_loop(self):
        """Same config on different loops → cache miss, two separate instances."""
        from app.infrastructure.llm.factory import LLMFactory

        call_count = 0
        fake_instance_a = {"mock": "llm-a"}
        fake_instance_b = {"mock": "llm-b"}
        instances = [fake_instance_a, fake_instance_b]

        async def _mock_create(*args, **kwargs):
            nonlocal call_count
            inst = instances[call_count]
            call_count += 1
            return inst

        async def _create_in_loop():
            from app.infrastructure.schemas import LLMConfig
            config = LLMConfig(model_name="gpt-4")
            return await LLMFactory.create_llm(config)

        with patch.object(LLMFactory, "_create_platform_llm", side_effect=_mock_create):
            # Run in two separate event loops (simulates Huey task behavior)
            instance_a = asyncio.run(_create_in_loop())
            instance_b = asyncio.run(_create_in_loop())

        assert instance_a is not instance_b, "Different loops must not share cached instance"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_cache_stats_counts_all_loops(self):
        """get_cache_stats sums instances across all cached loops."""
        from app.infrastructure.llm.factory import LLMFactory

        loop = asyncio.get_running_loop()
        LLMFactory._instance_cache[loop] = {
            "key1": MagicMock(),
            "key2": MagicMock(),
        }

        stats = LLMFactory.get_cache_stats()
        assert stats.cached_instances == 2
