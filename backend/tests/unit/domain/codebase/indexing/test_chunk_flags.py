"""Unit tests for P2.1: _update_api_chunk_flags and _update_db_chunk_flags."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.codebase.indexing.manager import IndexingManager


@pytest.fixture
def manager():
    return IndexingManager()


class TestUpdateApiChunkFlags:
    @pytest.mark.asyncio
    async def test_update_api_chunk_flags_called(self, manager):
        """Verify the method can be invoked without error under mock."""
        session = AsyncMock()
        mock_source_file = MagicMock()
        mock_source_file.id = 1

        mock_execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_source_file
        mock_execute.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=mock_execute)

        entities = [
            MagicMock(name="getUser", endpoint="/api/user", method="GET"),
        ]

        with pytest.MonkeyPatch().context() as m:
            m.setattr("app.domain.codebase.indexing.manager.session_scope", AsyncMock(return_value=session))
            result = await manager._update_api_chunk_flags(1, "routes/user.py", entities)
            assert result is None  # no exception

    @pytest.mark.asyncio
    async def test_update_api_chunk_flags_empty_entities(self, manager):
        """Empty entities list should be a no-op."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr("app.domain.codebase.indexing.manager.session_scope", AsyncMock(return_value=AsyncMock()))
            result = await manager._update_api_chunk_flags(1, "empty.py", [])
            assert result is None


class TestUpdateDbChunkFlags:
    @pytest.mark.asyncio
    async def test_update_db_chunk_flags_called(self, manager):
        """Verify the method can be invoked without error under mock."""
        session = AsyncMock()
        mock_source_file = MagicMock()
        mock_source_file.id = 1

        mock_execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_source_file
        mock_execute.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=mock_execute)

        tables = [
            MagicMock(table_name="users"),
            MagicMock(table_name="orders"),
        ]

        with pytest.MonkeyPatch().context() as m:
            m.setattr("app.domain.codebase.indexing.manager.session_scope", AsyncMock(return_value=session))
            result = await manager._update_db_chunk_flags(1, "models/user.py", tables)
            assert result is None

    @pytest.mark.asyncio
    async def test_update_db_chunk_flags_empty_tables(self, manager):
        """Empty tables list should be a no-op."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr("app.domain.codebase.indexing.manager.session_scope", AsyncMock(return_value=AsyncMock()))
            result = await manager._update_db_chunk_flags(1, "models/empty.py", [])
            assert result is None
