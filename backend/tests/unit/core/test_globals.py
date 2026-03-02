"""
Unit tests for globals module.
"""

import pytest

from app.core.globals import set_graph, get_graph
from app.core.persistence import (
    set_db_pool, get_db_pool,
    set_checkpointer, get_checkpointer
)


class TestGraphGlobals:
    """Tests for graph global functions."""

    def test_set_and_get_graph(self):
        """Test setting and getting graph."""
        mock_graph = {"nodes": ["a", "b"], "edges": []}
        set_graph(mock_graph)
        result = get_graph()
        assert result == mock_graph

    def test_get_graph_default_none(self):
        """Test getting graph when not set returns None."""
        # First reset to None
        set_graph(None)
        result = get_graph()
        assert result is None

    def test_graph_overwrite(self):
        """Test overwriting graph."""
        graph1 = {"nodes": ["a"]}
        graph2 = {"nodes": ["a", "b"]}
        set_graph(graph1)
        assert get_graph() == graph1
        set_graph(graph2)
        assert get_graph() == graph2

    def test_graph_any_type(self):
        """Test graph can be any type."""
        # Test with list
        set_graph(["node1", "node2"])
        assert get_graph() == ["node1", "node2"]
        # Test with string
        set_graph("graph_string")
        assert get_graph() == "graph_string"
        # Test with None
        set_graph(None)
        assert get_graph() is None


class TestPersistenceGlobals:
    """Tests for persistence global functions."""

    def test_set_and_get_db_pool(self):
        """Test setting and getting database pool."""
        mock_pool = MagicMock()
        set_db_pool(mock_pool)
        result = get_db_pool()
        assert result == mock_pool

    def test_get_db_pool_default_none(self):
        """Test getting db pool when not set returns None."""
        set_db_pool(None)
        result = get_db_pool()
        assert result is None

    def test_set_and_get_checkpointer(self):
        """Test setting and getting checkpointer."""
        mock_checkpointer = MagicMock()
        set_checkpointer(mock_checkpointer)
        result = get_checkpointer()
        assert result == mock_checkpointer

    def test_get_checkpointer_default_none(self):
        """Test getting checkpointer when not set returns None."""
        set_checkpointer(None)
        result = get_checkpointer()
        assert result is None

    def test_pool_and_checkpointer_independence(self):
        """Test pool and checkpointer are independent."""
        mock_pool = {"name": "pool"}
        mock_checkpointer = {"name": "checkpointer"}
        set_db_pool(mock_pool)
        set_checkpointer(mock_checkpointer)
        assert get_db_pool() == mock_pool
        assert get_checkpointer() == mock_checkpointer
        # Ensure they're not the same
        assert get_db_pool() != get_checkpointer()


from unittest.mock import MagicMock
