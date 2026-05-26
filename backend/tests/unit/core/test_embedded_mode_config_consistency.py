"""
Configuration consistency tests for EMBEDDED_MODE.

Validates that the Settings model correctly adjusts all infrastructure
configuration when EMBEDDED_MODE is toggled.
"""

import os
from unittest.mock import patch

import pytest


class TestConfigEmbeddedModeConsistency:
    """Tests for Settings._configure_embedded_mode validator."""

    @pytest.fixture
    def embedded_settings(self):
        """Create a Settings instance with EMBEDDED_MODE=true."""
        from app.core.config import Settings

        with patch.dict(os.environ, {"EMBEDDED_MODE": "true"}, clear=False):
            return Settings()

    @pytest.fixture
    def production_settings(self):
        """Create a Settings instance with EMBEDDED_MODE=false."""
        from app.core.config import Settings

        with patch.dict(os.environ, {"EMBEDDED_MODE": "false"}, clear=False):
            return Settings()

    # ------------------------------------------------------------------
    # Embedded mode: external services should be cleared
    # ------------------------------------------------------------------

    def test_embedded_mode_clears_neo4j_uri(self, embedded_settings):
        assert embedded_settings.NEO4J_URI is None

    def test_embedded_mode_clears_neo4j_user(self, embedded_settings):
        assert embedded_settings.NEO4J_USER is None

    def test_embedded_mode_clears_neo4j_password(self, embedded_settings):
        assert embedded_settings.NEO4J_PASSWORD is None

    def test_embedded_mode_clears_redis_url(self, embedded_settings):
        assert embedded_settings.REDIS_URL is None

    def test_embedded_mode_clears_meilisearch_url(self, embedded_settings):
        assert embedded_settings.MEILISEARCH_URL is None

    def test_embedded_mode_clears_meilisearch_api_key(self, embedded_settings):
        assert embedded_settings.MEILISEARCH_API_KEY is None

    def test_embedded_mode_sqlalchemy_uses_sqlite(self, embedded_settings):
        uri = embedded_settings.SQLALCHEMY_DATABASE_URI
        assert uri.startswith("sqlite+aiosqlite:///")

    def test_embedded_mode_vector_db_uri_is_none(self, embedded_settings):
        assert embedded_settings.VECTOR_DATABASE_URI is None

    def test_embedded_mode_all_external_uris_are_none(self, embedded_settings):
        """Batch assertion: all external service URIs should be None."""
        assert embedded_settings.NEO4J_URI is None
        assert embedded_settings.NEO4J_USER is None
        assert embedded_settings.NEO4J_PASSWORD is None
        assert embedded_settings.REDIS_URL is None
        assert embedded_settings.MEILISEARCH_URL is None
        assert embedded_settings.MEILISEARCH_API_KEY is None
        assert embedded_settings.VECTOR_DATABASE_URI is None

    # ------------------------------------------------------------------
    # Production mode: external services should be preserved
    # ------------------------------------------------------------------

    def test_production_mode_preserves_neo4j_config(self, production_settings):
        # Production mode should NOT clear Neo4j config (but actual value may be
        # overridden by env vars, so we only assert it's not None).
        assert production_settings.NEO4J_URI is not None
        assert production_settings.NEO4J_USER is not None

    def test_production_mode_preserves_redis_url(self, production_settings):
        assert production_settings.REDIS_URL is not None

    def test_production_mode_preserves_meilisearch_url(self, production_settings):
        assert production_settings.MEILISEARCH_URL is not None

    # ------------------------------------------------------------------
    # Cross-mode URI assertions
    # ------------------------------------------------------------------

    def test_sqlalchemy_uri_switches_between_modes(self):
        from app.core.config import Settings

        with patch.dict(os.environ, {"EMBEDDED_MODE": "true"}, clear=False):
            embedded = Settings()
            assert embedded.SQLALCHEMY_DATABASE_URI.startswith("sqlite")

        with patch.dict(os.environ, {"EMBEDDED_MODE": "false", "POSTGRES_SERVER": "db.example.com"}, clear=False):
            production = Settings()
            assert production.SQLALCHEMY_DATABASE_URI.startswith("postgresql")

    def test_vector_db_uri_switches_between_modes(self):
        from app.core.config import Settings

        with patch.dict(os.environ, {"EMBEDDED_MODE": "true"}, clear=False):
            embedded = Settings()
            assert embedded.VECTOR_DATABASE_URI is None

        with patch.dict(
            os.environ,
            {"EMBEDDED_MODE": "false", "POSTGRES_SERVER": "db.example.com", "VECTOR_POSTGRES_SERVER": "vector.example.com"},
            clear=False,
        ):
            production = Settings()
            assert production.VECTOR_DATABASE_URI is not None
            assert production.VECTOR_DATABASE_URI.startswith("postgresql")

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_embedded_mode_with_explicit_postgres_server_ignores_it(self):
        """Even if POSTGRES_SERVER is set, EMBEDDED_MODE=true forces SQLite."""
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {"EMBEDDED_MODE": "true", "POSTGRES_SERVER": "db.example.com"},
            clear=False,
        ):
            settings = Settings()
            assert settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite")

    def test_production_mode_with_postgres_server_uses_postgres(self):
        """When POSTGRES_SERVER is set and EMBEDDED_MODE=false, use PostgreSQL."""
        from app.core.config import Settings

        # Note: we can't easily test the 'no POSTGRES_SERVER' fallback because
        # Settings loads from ../.env file. We test the positive case instead.
        with patch.dict(os.environ, {"EMBEDDED_MODE": "false"}, clear=False):
            settings = Settings()
            if settings.POSTGRES_SERVER:
                assert settings.SQLALCHEMY_DATABASE_URI.startswith("postgresql")
            else:
                pytest.skip("POSTGRES_SERVER not configured in environment")
