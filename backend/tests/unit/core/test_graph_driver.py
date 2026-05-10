"""
Tests for graph driver adapter layer, including FileGraphDriver
MATCH + DETACH DELETE support and is_graph_enabled() abstraction.
"""

import json
import os
import tempfile

import pytest


class TestIsGraphEnabled:
    """Test that is_graph_enabled() works as a backend-agnostic check."""

    def test_is_graph_enabled_importable(self):
        """is_graph_enabled should be importable from driver module."""
        from app.infrastructure.database.graph.driver import is_graph_enabled
        assert callable(is_graph_enabled)

    def test_is_graph_enabled_returns_bool(self):
        """is_graph_enabled should return a boolean."""
        from app.infrastructure.database.graph.driver import is_graph_enabled
        result = is_graph_enabled()
        assert isinstance(result, bool)


class TestFileGraphDriverDelete:
    """Test FileGraphDriver MATCH + DETACH DELETE support."""

    @pytest.fixture
    def graph_driver(self):
        """Create a temporary FileGraphDriver instance."""
        from app.infrastructure.database.graph.file_graph import FileGraphDriver

        with tempfile.TemporaryDirectory() as tmpdir:
            driver = FileGraphDriver(data_dir=tmpdir)
            yield driver

    @pytest.fixture
    def graph_with_nodes(self, graph_driver):
        """Populate graph with test nodes."""
        G = graph_driver._graph
        # File nodes with project_id
        G.add_node("file1", project_id=1, path="src/main.py", type="file")
        G.add_node("file2", project_id=1, path="src/utils.py", type="file")
        G.add_node("file3", project_id=2, path="src/other.py", type="file")
        # Entity nodes (children of file1)
        G.add_node("entity1", project_id=1, type="function")
        G.add_node("entity2", project_id=1, type="class")
        # Edges: file1 CONTAINS entity1, entity2
        G.add_edge("file1", "entity1")
        G.add_edge("file1", "entity2")
        return graph_driver

    @pytest.mark.asyncio
    async def test_match_delete_by_project_id(self, graph_with_nodes):
        """MATCH ... DETACH DELETE should remove nodes by project_id."""
        driver = graph_with_nodes
        G = driver._graph

        # Initial state: 5 nodes
        assert G.number_of_nodes() == 5

        session = driver.session()
        async with session as s:
            result = await s.run(
                "MATCH (n {project_id: $pid}) DETACH DELETE n",
                pid=2,
            )
            data = await result.data()

        # file3 (project_id=2) should be deleted
        assert G.number_of_nodes() == 4
        assert "file3" not in G
        assert "file1" in G
        assert "file2" in G
        assert data[0]["deleted_count"] == 1

    @pytest.mark.asyncio
    async def test_match_delete_by_path(self, graph_with_nodes):
        """MATCH ... DETACH DELETE should remove nodes by path."""
        driver = graph_with_nodes
        G = driver._graph

        session = driver.session()
        async with session as s:
            await s.run(
                "MATCH (n {path: $path}) DETACH DELETE n",
                path="src/utils.py",
            )

        assert G.number_of_nodes() == 4
        assert "file2" not in G

    @pytest.mark.asyncio
    async def test_optional_match_delete_cascades(self, graph_with_nodes):
        """
        MATCH (f:File {project_id: $pid})
        OPTIONAL MATCH (f)-[:CONTAINS]->(e)
        DETACH DELETE e, f
        should delete File node and its successors.
        """
        driver = graph_with_nodes
        G = driver._graph

        assert G.number_of_nodes() == 5
        assert G.has_edge("file1", "entity1")
        assert G.has_edge("file1", "entity2")

        session = driver.session()
        async with session as s:
            result = await s.run(
                """
                MATCH (f {project_id: $pid})
                OPTIONAL MATCH (f)-[:CONTAINS]->(e)
                DETACH DELETE e
                DETACH DELETE f
                """,
                pid=1,
            )
            data = await result.data()

        # file1, entity1, entity2 should be deleted (3 nodes)
        # file2 (project_id=1 but no successors) should also be deleted
        # file3 (project_id=2) should remain
        assert G.number_of_nodes() == 1
        assert "file3" in G
        assert "file1" not in G
        assert "file2" not in G
        assert "entity1" not in G
        assert "entity2" not in G
        assert data[0]["deleted_count"] == 4

    @pytest.mark.asyncio
    async def test_delete_returns_count(self, graph_with_nodes):
        """Delete operation should return deleted_count in result."""
        driver = graph_with_nodes

        session = driver.session()
        async with session as s:
            result = await s.run(
                "MATCH (n {project_id: $pid}) DETACH DELETE n",
                pid=99,  # no match
            )
            data = await result.data()

        assert data[0]["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_no_match_no_error(self, graph_with_nodes):
        """Delete with no matching nodes should not raise."""
        driver = graph_with_nodes
        G = driver._graph

        session = driver.session()
        async with session as s:
            await s.run(
                "MATCH (n {project_id: $pid}) DETACH DELETE n",
                pid=999,
            )

        # All original nodes should remain
        assert G.number_of_nodes() == 5

    @pytest.mark.asyncio
    async def test_non_delete_match_still_works(self, graph_with_nodes):
        """Regular MATCH (without DETACH DELETE) should still return results."""
        driver = graph_with_nodes

        session = driver.session()
        async with session as s:
            result = await s.run(
                "MATCH (n {project_id: $pid}) RETURN n",
                pid=1,
            )
            data = await result.data()

        assert len(data) == 4  # file1, file2, entity1, entity2
