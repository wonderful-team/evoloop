"""
Factory dispatch tests for EMBEDDED_MODE.

Validates that every infrastructure factory function dispatches to the
correct backend implementation based on the EMBEDDED_MODE setting.

These tests use unittest.mock.patch to intercept class instantiation,
so they do NOT require real external services (PostgreSQL, Neo4j, Redis,
Meilisearch) to be running.
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings


class TestCacheFactory:
    """Tests for app.infrastructure.cache.get_cache()."""

    def test_embedded_returns_file_cache(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.infrastructure.cache.file.FileCache") as MockFileCache:
                from app.infrastructure.cache import get_cache

                # Reset singleton so get_cache() re-evaluates
                get_cache.__globals__["_cache_instance"] = None
                get_cache()
                MockFileCache.assert_called_once()

    def test_production_returns_redis_cache(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch("app.infrastructure.cache.redis.RedisCache") as MockRedisCache:
                from app.infrastructure.cache import get_cache

                get_cache.__globals__["_cache_instance"] = None
                get_cache()
                MockRedisCache.assert_called_once()


class TestSearchBackendFactory:
    """Tests for app.infrastructure.search.get_search_backend()."""

    def test_embedded_auto_selects_sqlite_fts(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch.object(settings, "SEARCH_ENGINE", "auto"):
                with patch("app.infrastructure.search.sqlite_fts.SQLiteFTSBackend") as MockSQLite:
                    from app.infrastructure.search import get_search_backend

                    get_search_backend.__globals__["_search_backend"] = None
                    get_search_backend()
                    MockSQLite.assert_called_once()

    def test_production_auto_selects_meilisearch(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch.object(settings, "SEARCH_ENGINE", "auto"):
                with patch("app.infrastructure.search.meilisearch.MeilisearchBackend") as MockMeili:
                    from app.infrastructure.search import get_search_backend

                    get_search_backend.__globals__["_search_backend"] = None
                    get_search_backend()
                    MockMeili.assert_called_once()

    def test_explicit_sqlite_fts_overrides_auto(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch.object(settings, "SEARCH_ENGINE", "sqlite_fts"):
                with patch("app.infrastructure.search.sqlite_fts.SQLiteFTSBackend") as MockSQLite:
                    from app.infrastructure.search import get_search_backend

                    get_search_backend.__globals__["_search_backend"] = None
                    get_search_backend()
                    MockSQLite.assert_called_once()

    def test_explicit_meilisearch_overrides_auto(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch.object(settings, "SEARCH_ENGINE", "meilisearch"):
                with patch("app.infrastructure.search.meilisearch.MeilisearchBackend") as MockMeili:
                    from app.infrastructure.search import get_search_backend

                    get_search_backend.__globals__["_search_backend"] = None
                    get_search_backend()
                    MockMeili.assert_called_once()


class TestGraphDriverFactory:
    """Tests for app.infrastructure.database.graph.driver.GraphManager."""

    @pytest.mark.asyncio
    async def test_embedded_returns_file_graph_driver(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.infrastructure.database.graph.file_graph.FileGraphDriver") as MockFileGraph:
                from app.infrastructure.database.graph.driver import GraphManager

                GraphManager._drivers.clear()
                GraphManager._use_neo4j = False
                driver = GraphManager.get_driver()
                MockFileGraph.assert_called_once()

    @pytest.mark.asyncio
    async def test_production_returns_neo4j_driver(self):
        import sys
        # Ensure real neo4j package is loaded (it may not be in sys.modules yet)
        if "neo4j" not in sys.modules:
            import neo4j

        with patch.object(settings, "EMBEDDED_MODE", False):
            import app.infrastructure.database.graph.neo4j as _neo4j_mod
            with patch.object(_neo4j_mod, "Neo4jDriver") as MockNeo4j:
                from app.infrastructure.database.graph.driver import GraphManager

                GraphManager._drivers.clear()
                GraphManager._use_neo4j = True
                driver = GraphManager.get_driver()
                MockNeo4j.assert_called_once()

    def test_graph_manager_is_enabled_false_when_embedded(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            from app.infrastructure.database.graph.driver import GraphManager

            GraphManager._use_neo4j = False
            assert GraphManager.is_enabled() is False

    def test_graph_manager_is_enabled_true_when_production(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            from app.infrastructure.database.graph.driver import GraphManager

            GraphManager._use_neo4j = True
            assert GraphManager.is_enabled() is True


class TestEventBusFactory:
    """Tests for app.core.engine.message.event_bus.get_event_bus()."""

    def test_embedded_returns_local_event_bus(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.core.engine.message.event_bus.LocalEventBus") as MockLocal:
                from app.core.engine.message.event_bus import get_event_bus, _event_bus

                get_event_bus.__globals__["_event_bus"] = None
                get_event_bus()
                MockLocal.assert_called_once()

    def test_production_returns_distributed_event_bus(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch("app.core.engine.message.event_bus.DistributedEventBus") as MockDist:
                from app.core.engine.message.event_bus import get_event_bus

                get_event_bus.__globals__["_event_bus"] = None
                get_event_bus()
                MockDist.assert_called_once()


class TestEmbedderFactory:
    """Tests for app.infrastructure.embeddings.factory.EmbedderFactory."""

    def test_embedded_fallback_to_local_embedder(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.infrastructure.embeddings.factory.LocalEmbedder") as MockLocal:
                from app.infrastructure.embeddings.factory import EmbedderFactory

                EmbedderFactory.get_embedder()
                MockLocal.assert_called_once()

    @pytest.mark.skip(reason="Requires external API configuration")
    def test_production_uses_configured_provider(self):
        """Placeholder: production embedder selection depends on env config."""
        pass


class TestQueueFactory:
    """Tests for app.infrastructure.queue.factory.get_scheduler().

    NOTE: conftest.py mocks the scheduler globally. These tests verify
    that the *factory logic* itself branches correctly by inspecting
    the factory's internal mode selection.
    """

    def test_embedded_auto_selects_huey(self):
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch.object(settings, "TASK_QUEUE_BACKEND", "auto"):
                with patch("app.infrastructure.queue.huey_queue.HueyTaskScheduler") as MockHuey:
                    from app.infrastructure.queue.factory import create_task_scheduler

                    create_task_scheduler.__globals__["_scheduler"] = None
                    create_task_scheduler()
                    MockHuey.assert_called_once()

    def test_production_auto_selects_celery(self):
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch.object(settings, "TASK_QUEUE_BACKEND", "auto"):
                # Patch the real celery.Celery class (imported inside create_celery_app)
                with patch("celery.Celery") as MockCelery:
                    from app.infrastructure.queue.factory import create_task_scheduler

                    create_task_scheduler.__globals__["_scheduler"] = None
                    create_task_scheduler()
                    MockCelery.assert_called_once()
