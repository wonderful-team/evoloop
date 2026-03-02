"""
Unit tests for memory system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


class TestMemoryManager:
    """Tests for MemoryManager facade."""

    def test_initialization(self):
        """Test memory manager initialization."""
        from app.core.memory.manager import MemoryManager

        # Create with mocked backends
        manager = MemoryManager()

        assert manager.short_term is not None
        assert manager.long_term is not None
        assert manager.preferences is not None
        assert manager.graph is not None

    @pytest.mark.asyncio
    async def test_initialize_all(self):
        """Test initializing all backends."""
        from app.core.memory.manager import MemoryManager

        manager = MemoryManager()
        manager.short_term = AsyncMock()
        manager.long_term = AsyncMock()
        manager.preferences = AsyncMock()
        manager.graph = AsyncMock()

        await manager.initialize()

        manager.short_term.initialize.assert_called_once()
        manager.long_term.initialize.assert_called_once()
        manager.preferences.initialize.assert_called_once()
        manager.graph.initialize.assert_called_once()


class TestSqlShortTermMemory:
    """Tests for SQL-based short-term memory."""

    @pytest.mark.asyncio
    async def test_add_message(self):
        """Test adding a message."""
        from app.core.memory.backends.sql_short_term import SqlShortTermMemory

        memory = SqlShortTermMemory()

        # Mock session_scope
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar = MagicMock(return_value=0)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch('app.core.memory.backends.sql_short_term.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            message = HumanMessage(content="Test message")
            await memory.add_message("thread-123", message)

            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_context(self):
        """Test retrieving conversation context."""
        from app.core.memory.backends.sql_short_term import SqlShortTermMemory

        memory = SqlShortTermMemory()

        # Mock session_scope
        mock_session = AsyncMock()

        # Create mock message records
        mock_record1 = MagicMock()
        mock_record1.role = "human"
        mock_record1.content = "Message 1"

        mock_record2 = MagicMock()
        mock_record2.role = "ai"
        mock_record2.content = "Response 1"

        # The actual code queries in descending order and reverses
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record2, mock_record1]  # DB returns desc
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch('app.core.memory.backends.sql_short_term.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            messages = await memory.get_context("thread-123", limit=10)

            assert len(messages) == 2
            assert messages[0].content == "Message 1"  # After reverse, human first
            assert messages[1].content == "Response 1"  # AI second


class TestNeo4jLongTermMemory:
    """Tests for Neo4j-based long-term memory."""

    def _create_mock_driver(self):
        """Helper to create a properly configured mock Neo4j driver."""
        mock_driver = MagicMock()
        mock_session = AsyncMock()

        # Create a session context manager mock
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        # driver.session() returns the context manager
        mock_driver.session = MagicMock(return_value=session_cm)

        return mock_driver, mock_session

    @pytest.mark.asyncio
    async def test_store_concept(self):
        """Test storing a concept."""
        from app.core.memory.backends.neo4j_long_term import Neo4jLongTermMemory
        from app.core.memory.interfaces.long_term import Concept

        memory = Neo4jLongTermMemory()

        concept = Concept(
            name="TestConcept",
            description="A test concept",
            project_id=1
        )

        mock_driver, mock_session = self._create_mock_driver()

        with patch('app.core.memory.backends.neo4j_long_term.get_graph_db', return_value=mock_driver):
            # Mock the embedder
            mock_embedder = MagicMock()
            mock_embedder.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
            with patch('app.core.memory.backends.neo4j_long_term.EmbedderFactory.get_embedder', return_value=mock_embedder):
                await memory.store_concept(concept)

                # Verify session was used
                mock_session.run.assert_called()

    @pytest.mark.asyncio
    async def test_search_concepts_data(self):
        """Test searching concepts data."""
        from app.core.memory.backends.neo4j_long_term import Neo4jLongTermMemory

        memory = Neo4jLongTermMemory()

        mock_driver, mock_session = self._create_mock_driver()

        # Mock the result data
        mock_records = [
            {"name": "TestConcept", "description": "Test description", "project_id": 1},
        ]
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(return_value=mock_records)
        mock_session.run.return_value = mock_result

        with patch('app.core.memory.backends.neo4j_long_term.get_graph_db', return_value=mock_driver):
            # Mock the embedder
            mock_embedder = MagicMock()
            mock_embedder.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
            with patch('app.core.memory.backends.neo4j_long_term.EmbedderFactory.get_embedder', return_value=mock_embedder):
                results = await memory.search_concepts_data("test query", project_id=1)

                assert len(results) == 1
                assert results[0]["name"] == "TestConcept"


class TestNeo4jPreferenceStore:
    """Tests for Neo4j-based preference store."""

    def _create_mock_driver(self):
        """Helper to create a properly configured mock Neo4j driver."""
        mock_driver = MagicMock()
        mock_session = AsyncMock()

        # Create a session context manager mock
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        # driver.session() returns the context manager
        mock_driver.session = MagicMock(return_value=session_cm)

        return mock_driver, mock_session

    @pytest.mark.asyncio
    async def test_set_preference(self):
        """Test saving a preference."""
        from app.core.memory.backends.neo4j_preferences import Neo4jPreferenceStore

        store = Neo4jPreferenceStore()

        mock_driver, mock_session = self._create_mock_driver()

        with patch('app.core.memory.backends.neo4j_preferences.get_graph_db', return_value=mock_driver):
            await store.set_preference("user-123", "theme", "dark")
            mock_session.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_merged_preferences(self):
        """Test retrieving merged preferences."""
        from app.core.memory.backends.neo4j_preferences import Neo4jPreferenceStore

        store = Neo4jPreferenceStore()

        mock_driver, mock_session = self._create_mock_driver()

        # Mock the result data
        mock_records = [
            {"key": "theme", "value": "dark", "desc": "UI Theme", "pid": 0},
        ]
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(return_value=mock_records)
        mock_session.run.return_value = mock_result

        with patch('app.core.memory.backends.neo4j_preferences.get_graph_db', return_value=mock_driver):
            result = await store.get_merged_preferences("user-123")
            assert "dark" in result
            assert "theme" in result


class TestDiffTracker:
    """Tests for diff tracking."""

    def test_capture_snapshot(self):
        """Test capturing file snapshot."""
        from app.core.memory.diff import DiffTracker
        import tempfile
        import os

        tracker = DiffTracker()

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("original content")
            temp_path = f.name

        try:
            tracker.capture_snapshot(temp_path, "thread-123")

            snapshot = tracker._snapshots.get(f"thread-123:{temp_path}")
            assert snapshot is not None
            assert snapshot == "original content"
        finally:
            os.unlink(temp_path)

    def test_compute_diff(self):
        """Test computing file diff."""
        from app.core.memory.diff import DiffTracker
        import tempfile
        import os

        tracker = DiffTracker()

        # Create temp file and capture snapshot
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("original content")
            temp_path = f.name

        try:
            tracker.capture_snapshot(temp_path, "thread-123")

            # Modify the file
            with open(temp_path, 'w') as f:
                f.write("modified content")

            operation, diff, original = tracker.compute_diff(temp_path, "thread-123")

            assert operation == "EDIT"
            assert original == "original content"
            assert "modified" in diff
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
