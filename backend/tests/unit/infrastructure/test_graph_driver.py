"""
Unit tests for Neo4j graph database driver.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.database.graph.driver import Neo4jManager, get_graph_db


class TestNeo4jManager:
    """Tests for Neo4jManager."""

    def test_get_driver_no_event_loop(self):
        """Test get_driver raises error without event loop."""
        with patch('asyncio.get_running_loop', side_effect=RuntimeError):
            with pytest.raises(RuntimeError, match="Cannot get Neo4j driver without a running event loop"):
                Neo4jManager.get_driver()

    @pytest.mark.asyncio
    async def test_get_driver_creates_new_driver(self):
        """Test get_driver creates new driver for new loop."""
        mock_driver = MagicMock()

        with patch('asyncio.get_running_loop', return_value=asyncio.get_running_loop()):
            with patch('app.infrastructure.database.graph.driver.AsyncGraphDatabase.driver', return_value=mock_driver):
                # Clear any existing drivers
                Neo4jManager._drivers.clear()

                driver = Neo4jManager.get_driver()
                assert driver == mock_driver

    @pytest.mark.asyncio
    async def test_get_driver_reuses_existing_driver(self):
        """Test get_driver reuses driver for same loop."""
        mock_driver = MagicMock()
        loop = asyncio.get_running_loop()
        Neo4jManager._drivers[loop] = mock_driver

        with patch('asyncio.get_running_loop', return_value=loop):
            driver = Neo4jManager.get_driver()
            assert driver == mock_driver

        # Cleanup
        Neo4jManager._drivers.clear()

    @pytest.mark.asyncio
    async def test_close_driver_closes_current_loop_driver(self):
        """Test close_driver closes driver for current loop."""
        mock_driver = AsyncMock()
        loop = asyncio.get_running_loop()
        Neo4jManager._drivers[loop] = mock_driver

        with patch('asyncio.get_running_loop', return_value=loop):
            await Neo4jManager.close_driver()

        mock_driver.close.assert_called_once()
        assert loop not in Neo4jManager._drivers

    @pytest.mark.asyncio
    async def test_close_driver_no_loop(self):
        """Test close_driver handles no running loop."""
        with patch('asyncio.get_running_loop', side_effect=RuntimeError):
            # Should not raise
            await Neo4jManager.close_driver()

    @pytest.mark.asyncio
    async def test_close_all_closes_all_drivers(self):
        """Test close_all closes all drivers."""
        mock_driver1 = AsyncMock()
        mock_driver2 = AsyncMock()

        # Create fake loops
        loop1 = MagicMock()
        loop2 = MagicMock()

        Neo4jManager._drivers[loop1] = mock_driver1
        Neo4jManager._drivers[loop2] = mock_driver2

        await Neo4jManager.close_all()

        mock_driver1.close.assert_called_once()
        mock_driver2.close.assert_called_once()
        assert len(Neo4jManager._drivers) == 0

    @pytest.mark.asyncio
    async def test_close_all_handles_errors(self):
        """Test close_all handles driver close errors."""
        mock_driver = AsyncMock()
        mock_driver.close.side_effect = Exception("Close error")

        loop = MagicMock()
        Neo4jManager._drivers[loop] = mock_driver

        # Should not raise
        await Neo4jManager.close_all()

        assert len(Neo4jManager._drivers) == 0


class TestGetGraphDb:
    """Tests for get_graph_db function."""

    @pytest.mark.asyncio
    async def test_get_graph_db_returns_driver(self):
        """Test get_graph_db returns driver."""
        mock_driver = MagicMock()
        loop = asyncio.get_running_loop()
        Neo4jManager._drivers[loop] = mock_driver

        with patch('asyncio.get_running_loop', return_value=loop):
            driver = await get_graph_db()
            assert driver == mock_driver

        # Cleanup
        Neo4jManager._drivers.clear()
