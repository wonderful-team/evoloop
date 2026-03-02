"""
Unit tests for SQL database module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.database.sql.database import (
    get_db,
    session_scope,
    AsyncSessionLocal,
    engine,
)


class TestDatabaseConnection:
    """Tests for database connection."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """Test get_db dependency yields a session."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("app.infrastructure.database.sql.database.AsyncSessionLocal") as mock_session_factory:
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            async for session in get_db():
                assert session == mock_session
                break

    @pytest.mark.asyncio
    async def test_get_db_rollback_on_error(self):
        """Test get_db rolls back on error."""
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("app.infrastructure.database.sql.database.AsyncSessionLocal") as mock_session_factory:
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            try:
                async for session in get_db():
                    raise ValueError("Test error")
            except ValueError:
                pass


class TestSessionScope:
    """Tests for session_scope context manager."""

    @pytest.mark.asyncio
    async def test_session_scope_commits_on_success(self):
        """Test session_scope commits when no exception."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("app.infrastructure.database.sql.database.AsyncSessionLocal") as mock_session_factory:
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            async with session_scope() as session:
                assert session == mock_session

            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_not_called()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_scope_rollback_on_error(self):
        """Test session_scope rolls back on exception."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("app.infrastructure.database.sql.database.AsyncSessionLocal") as mock_session_factory:
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(ValueError):
                async with session_scope() as session:
                    raise ValueError("Test error")

            mock_session.commit.assert_not_called()
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    def test_get_db_session_alias(self):
        """Test get_db_session is alias for session_scope."""
        from app.infrastructure.database.sql.database import get_db_session
        assert get_db_session == session_scope


class TestDatabaseEngine:
    """Tests for database engine configuration."""

    def test_engine_exists(self):
        """Test engine is created."""
        assert engine is not None

    def test_async_session_local_exists(self):
        """Test AsyncSessionLocal is created."""
        assert AsyncSessionLocal is not None
