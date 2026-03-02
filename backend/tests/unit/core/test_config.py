"""
Unit tests for configuration module.
"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_values(self):
        """Test that default settings are correctly initialized."""
        # Import here to avoid loading env vars at module level
        with patch.dict(os.environ, {}, clear=True):
            with patch('app.core.config.Settings._default_projects_root', return_value='/tmp/projects'):
                from app.core.config import Settings

                settings = Settings(
                    PROJECT_NAME="TestProject",
                    POSTGRES_SERVER="localhost",
                    POSTGRES_USER="testuser",
                )

                assert settings.API_V1_STR == "/api/v1"
                assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 11520  # 60 * 24 * 8
                assert settings.FRONTEND_HOST == "http://localhost:5173"
                assert settings.ENVIRONMENT == "local"
                # EXECUTION_MODE may be overridden by env, just check it has a valid value
                assert settings.EXECUTION_MODE in ["local", "docker"]
                assert settings.SANDBOX_IMAGE == "evoloop-sandbox"

    def test_postgres_dsn_construction(self):
        """Test PostgreSQL DSN construction."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_PORT=5432,
                POSTGRES_USER="testuser",
                POSTGRES_PASSWORD="testpass",
                POSTGRES_DB="testdb",
            )

            dsn = str(settings.SQLALCHEMY_DATABASE_URI)
            assert "postgresql+psycopg" in dsn
            assert "testuser" in dsn
            assert "testpass" in dsn
            assert "localhost" in dsn
            assert "5432" in dsn
            assert "testdb" in dsn

    def test_checkpointer_dsn_construction(self):
        """Test Checkpointer DSN construction."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_PORT=5432,
                POSTGRES_USER="testuser",
                POSTGRES_PASSWORD="testpass",
                POSTGRES_DB="testdb",
            )

            dsn = settings.CHECKPOINTER_DATABASE_URI
            assert "postgresql" in dsn
            assert "testuser" in dsn

    def test_all_cors_origins(self):
        """Test CORS origins computation."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
                FRONTEND_HOST="http://localhost:3000",
                BACKEND_CORS_ORIGINS=["http://example.com", "https://test.com"],
            )

            origins = settings.all_cors_origins
            assert "http://localhost:3000" in origins
            assert "http://example.com" in origins
            assert "https://test.com" in origins

    def test_emails_enabled(self):
        """Test email enabled property."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            # Without SMTP config
            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )
            assert settings.emails_enabled is False

            # With SMTP config
            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
                SMTP_HOST="smtp.example.com",
                EMAILS_FROM_EMAIL="test@example.com",
            )
            assert settings.emails_enabled is True

    def test_default_emails_from(self):
        """Test default emails from name validator."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="MyProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )

            assert settings.EMAILS_FROM_NAME == "MyProject"

    def test_app_data_dir(self):
        """Test application data directory property."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )

            assert ".evoloop" in settings.APP_DATA_DIR

    def test_directories_created(self):
        """Test that artifact directories are created."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.makedirs') as mock_makedirs:
                from app.core.config import Settings

                settings = Settings(
                    PROJECT_NAME="TestProject",
                    POSTGRES_SERVER="localhost",
                    POSTGRES_USER="testuser",
                )

                # Access properties that should create directories
                _ = settings.BROWSER_ARTIFACTS_DIR
                _ = settings.SCREENSHOTS_DIR
                _ = settings.LIBRARY_ROOT

                # Verify makedirs was called
                assert mock_makedirs.called

    def test_embedding_config(self):
        """Test embedding configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )

            assert settings.EMBEDDING_PROVIDER == "openai"
            # Embedding model may be overridden by env, just check it has a value
            assert settings.EMBEDDING_MODEL_NAME is not None
            assert settings.EMBEDDING_DIMENSIONS > 0

    def test_memory_config(self):
        """Test memory configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )

            assert settings.MEMORY_SEARCH_LIMIT == 5
            assert settings.MAX_SESSION_HISTORY == 20
            assert settings.MEMORY_RELEVANCE_THRESHOLD == 0.75
            assert settings.MAX_MEMORY_ITEMS == 1000

    def test_rag_config(self):
        """Test RAG and search configuration defaults."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            settings = Settings(
                PROJECT_NAME="TestProject",
                POSTGRES_SERVER="localhost",
                POSTGRES_USER="testuser",
            )

            assert settings.DEFAULT_SEARCH_TOP_K == 10
            assert settings.MAX_SEARCH_DEPTH == 3
            assert settings.MIN_RELEVANCE_SCORE == 0.6
            assert settings.DEFAULT_CHUNK_SIZE == 1000
            assert settings.MAX_CHUNK_SIZE == 4000
            assert settings.DEFAULT_CHUNK_OVERLAP == 200


class TestParseCors:
    """Tests for parse_cors function."""

    def test_parse_comma_separated_string(self):
        """Test parsing comma-separated CORS string."""
        from app.core.config import parse_cors

        result = parse_cors("http://localhost:3000, https://example.com")
        assert result == ["http://localhost:3000", "https://example.com"]

    def test_parse_list(self):
        """Test parsing CORS as list."""
        from app.core.config import parse_cors

        result = parse_cors(["http://localhost:3000", "https://example.com"])
        assert result == ["http://localhost:3000", "https://example.com"]

    def test_parse_single_string(self):
        """Test parsing single CORS string without commas."""
        from app.core.config import parse_cors

        result = parse_cors("http://localhost:3000")
        assert result == ["http://localhost:3000"]

    def test_parse_invalid_value(self):
        """Test parsing invalid CORS value raises error."""
        from app.core.config import parse_cors

        with pytest.raises(ValueError):
            parse_cors(12345)


class TestDefaultProjectsRoot:
    """Tests for _default_projects_root function."""

    def test_default_projects_root_with_existing_candidates(self, tmp_path):
        """Test projects root when candidates exist."""
        from app.core.config import Settings

        # Create a temporary "项目" directory
        projects_dir = tmp_path / "项目"
        projects_dir.mkdir()

        with patch('os.path.expanduser', return_value=str(tmp_path)):
            result = Settings._default_projects_root()
            assert "项目" in result

    def test_default_projects_root_fallback_to_home(self, tmp_path):
        """Test projects root falls back to home when no candidates exist."""
        from app.core.config import Settings

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch('os.path.expanduser', return_value=str(empty_dir)):
            result = Settings._default_projects_root()
            assert result == str(empty_dir)


class TestSecretValidation:
    """Tests for secret validation."""

    def test_check_default_secret_warning_in_local(self):
        """Test default secret warning in local environment."""
        import warnings

        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                settings = Settings(
                    PROJECT_NAME="TestProject",
                    POSTGRES_SERVER="localhost",
                    POSTGRES_USER="testuser",
                    SECRET_KEY="changethis",
                    ENVIRONMENT="local",
                )

                # Force validation
                settings._enforce_non_default_secrets()

                # Should emit a warning in local environment
                assert len(w) >= 1

    def test_check_default_secret_raises_in_production(self):
        """Test default secret raises error in production."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings

            with pytest.raises(ValueError, match="changethis"):
                Settings(
                    PROJECT_NAME="TestProject",
                    POSTGRES_SERVER="localhost",
                    POSTGRES_USER="testuser",
                    SECRET_KEY="changethis",
                    ENVIRONMENT="production",
                )
