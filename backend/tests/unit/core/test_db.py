"""
Unit tests for database module.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestEngine:
    """Tests for database engine."""

    def test_engine_exists(self):
        """Test that engine is imported and available."""
        from app.core.db import engine

        # Engine should exist after import
        assert engine is not None


class TestInitDb:
    """Tests for init_db function."""

    def test_init_db_empty(self):
        """Test that init_db does nothing (tables managed by Alembic)."""
        from app.core.db import init_db

        mock_session = MagicMock()
        result = init_db(mock_session)

        # Should return None and not interact with session
        assert result is None
        mock_session.assert_not_called()
