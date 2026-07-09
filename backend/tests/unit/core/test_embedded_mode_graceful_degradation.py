"""
Graceful Degradation Tests for EMBEDDED_MODE (Phase 5)

Validates that production-mode factories fall back to embedded-compatible
backends when external dependencies are missing or misconfigured.

These tests use mocking to simulate failure conditions and do NOT require
real external services.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.core.config import settings


class TestQueueFactoryFallback:
    """Validate task scheduler fallback when Celery is unavailable."""

    def test_production_mode_creates_celery(self):
        """EMBEDDED_MODE=false → Celery scheduler."""
        pytest.importorskip("celery")
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch("celery.Celery") as MockCelery:
                import app.infrastructure.queue.factory as _factory_mod

                _factory_mod._scheduler = None
                _factory_mod.create_task_scheduler()
                MockCelery.assert_called()

    def test_embedded_mode_creates_huey(self):
        """EMBEDDED_MODE=true → Huey scheduler."""
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.infrastructure.queue.huey_queue.HueyTaskScheduler") as MockHuey:
                import app.infrastructure.queue.factory as _factory_mod

                _factory_mod._scheduler = None
                _factory_mod.create_task_scheduler()
                MockHuey.assert_called_once()


class TestEmbedderFactoryFallback:
    """Validate embedder fallback when remote provider is unconfigured."""

    def test_no_provider_falls_back_to_local_embedder(self):
        """No embedding provider configured → LocalEmbedder."""
        from app.infrastructure.embeddings.factory import EmbedderFactory
        EmbedderFactory._instances.clear()
        with patch("app.infrastructure.embeddings.factory.SystemConfigService.get_value", return_value=None):
            with patch.object(settings, "EMBEDDED_MODE", True), patch.object(settings, "EMBEDDING_ENABLED", True):
                # Patch the class reference bound in factory module
                with patch("app.infrastructure.embeddings.factory.LocalEmbedder") as MockLocal:
                    EmbedderFactory.get_embedder()
                    MockLocal.assert_called_once()

    def test_sentence_transformers_missing_raises_in_production(self):
        """Production mode without sentence_transformers → returns None gracefully."""
        from app.infrastructure.embeddings.factory import EmbedderFactory
        EmbedderFactory._instances.clear()
        with patch("app.infrastructure.embeddings.factory.SystemConfigService.get_value", return_value=None):
            with patch.object(settings, "EMBEDDED_MODE", False), patch.object(settings, "EMBEDDING_ENABLED", True):
                with patch.dict("sys.modules", {"sentence_transformers": None}):
                    assert EmbedderFactory.get_embedder() is None



class TestSearchBackendExplicitOverride:
    """Validate that explicit backend choice overrides auto-detection."""

    def test_explicit_sqlite_fts_in_production(self):
        """SEARCH_ENGINE=sqlite_fts in production → SQLiteFTSBackend."""
        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch.object(settings, "SEARCH_ENGINE", "sqlite_fts"):
                with patch("app.infrastructure.search.sqlite_fts.SQLiteFTSBackend") as MockSQLite:
                    from app.infrastructure.search import get_search_backend

                    # Reset singleton
                    import app.infrastructure.search as _search_mod

                    _search_mod._search_backend = None
                    get_search_backend()
                    MockSQLite.assert_called_once()

    def test_explicit_meilisearch_in_embedded(self):
        """SEARCH_ENGINE=meilisearch in embedded → MeilisearchBackend."""
        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch.object(settings, "SEARCH_ENGINE", "meilisearch"):
                with patch("app.infrastructure.search.meilisearch.MeilisearchBackend") as MockMeili:
                    from app.infrastructure.search import get_search_backend

                    import app.infrastructure.search as _search_mod

                    _search_mod._search_backend = None
                    get_search_backend()
                    MockMeili.assert_called_once()
