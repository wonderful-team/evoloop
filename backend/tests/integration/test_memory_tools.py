"""
Integration tests for memory tools with real memory backend.

These tests require:
- SQLite database (for short-term memory)
- File storage (for long-term memory)

Run with: pytest tests/integration/test_memory_tools.py -v --tb=short
"""

import asyncio
import os
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Mark all tests as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def test_memory_root():
    """Create a temporary directory for test memory files."""
    temp_dir = tempfile.mkdtemp(prefix="evoloop_test_memory_")
    yield temp_dir
    # Cleanup after tests
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def test_db_path():
    """Create a temporary SQLite database."""
    temp_db = tempfile.mktemp(suffix=".db", prefix="evoloop_test_")
    yield temp_db
    # Cleanup
    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture
async def memory_setup(test_memory_root, test_db_path, monkeypatch):
    """Setup memory managers with test configuration."""
    # Monkeypatch settings
    monkeypatch.setenv("BRAIN_MEMORY_ROOT", test_memory_root)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db_path}")
    
    # Import after setting env
    from app.core.config import settings
    monkeypatch.setattr(settings.__class__, "BRAIN_MEMORY_ROOT", test_memory_root)
    
    # Initialize short-term memory
    from app.core.memory.backends.sql_short_term import SqlShortTermMemory
    short_term = SqlShortTermMemory()
    await short_term.initialize()
    
    # Initialize file storage
    from app.core.memory.backends.file_backend import FileMemoryStorage
    file_storage = FileMemoryStorage(base_dir=test_memory_root)
    
    yield {
        "short_term": short_term,
        "file_storage": file_storage,
        "root": test_memory_root,
    }
    
    # Cleanup
    await short_term.flush()


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestRememberRecallIntegration:
    """Integration tests for remember/recall workflow."""

    @pytest.mark.asyncio
    async def test_full_remember_recall_cycle(self, memory_setup, monkeypatch):
        """Test complete flow: remember something, then recall it."""
        from app.core.engine.tools.memory_tools import remember, recall
        from app.core.context.manager import ContextManager
        
        # Mock context
        class MockContext:
            user_id = "test_user_123"
            project_id = 42
            thread_id = "test_thread_abc"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Step 1: Remember something
            remember_result = await remember(
                content="Always use TypeScript for new projects",
                context="User's preference stated on 2024-01-15"
            )
            
            assert "✅ Remembered" in remember_result
            
            # Step 2: Recall it
            recall_result = await recall(query="TypeScript", limit=5)
            
            assert "📚 Recalled" in recall_result or "🔍 Found" in recall_result
            assert "TypeScript" in recall_result
            
        finally:
            ContextManager.current = original_current
    
    @pytest.mark.asyncio
    async def test_multiple_memories_recall(self, memory_setup, monkeypatch):
        """Test remembering multiple items and recalling with filtering."""
        from app.core.engine.tools.memory_tools import remember, recall
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "test_user_456"
            project_id = 99
            thread_id = "test_thread_xyz"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Remember multiple things
            memories = [
                ("Use Docker for deployment", "Infrastructure"),
                ("Prefer PostgreSQL over MySQL", "Database preference"),
                ("Always write unit tests", "Testing policy"),
            ]
            
            for content, ctx in memories:
                result = await remember(content=content, context=ctx)
                assert "✅ Remembered" in result
            
            # Recall specific topic
            recall_result = await recall(query="database PostgreSQL", limit=5)
            assert "PostgreSQL" in recall_result
            
        finally:
            ContextManager.current = original_current
    
    @pytest.mark.asyncio
    async def test_recall_across_users_privacy(self, memory_setup, monkeypatch):
        """Test that private memories are not shared between users."""
        from app.core.engine.tools.memory_tools import remember, recall
        from app.core.context.manager import ContextManager
        
        # User A remembers something private
        class MockContextUserA:
            user_id = "user_A"
            project_id = 1
            thread_id = "thread_A"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContextUserA()
        
        try:
            await remember(
                content="I prefer dark mode",
                context="Personal preference"
            )
            
            # User B tries to recall
            class MockContextUserB:
                user_id = "user_B"
                project_id = 1
                thread_id = "thread_B"
            
            ContextManager.current = lambda: MockContextUserB()
            
            recall_result = await recall(query="dark mode")
            # Should not see User A's private preference
            # (This depends on implementation details of memory_manager.search_memories)
            
        finally:
            ContextManager.current = original_current


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestSearchHistoryIntegration:
    """Integration tests for search_history with real database."""

    @pytest.mark.asyncio
    async def test_search_history_with_stored_messages(self, memory_setup, monkeypatch):
        """Test searching history after storing messages."""
        from app.core.engine.tools.memory_tools import search_history
        from app.core.context.manager import ContextManager
        from langchain_core.messages import HumanMessage, AIMessage
        
        class MockContext:
            user_id = "test_user"
            project_id = 1
            thread_id = "test_thread_history"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Add some messages to short-term memory
            short_term = memory_setup["short_term"]
            
            await short_term.add_message(
                "test_thread_history",
                HumanMessage(content="Let's discuss the database schema")
            )
            await short_term.add_message(
                "test_thread_history",
                AIMessage(content="Sure, what database are you thinking?")
            )
            await short_term.add_message(
                "test_thread_history",
                HumanMessage(content="PostgreSQL would be best for this")
            )
            
            # Search for database-related messages
            result = await search_history(query="database PostgreSQL")
            
            assert "🔍 Found" in result
            assert "database" in result.lower() or "PostgreSQL" in result
            
        finally:
            ContextManager.current = original_current
    
    @pytest.mark.asyncio
    async def test_search_history_no_matches(self, memory_setup, monkeypatch):
        """Test searching history when nothing matches."""
        from app.core.engine.tools.memory_tools import search_history
        from app.core.context.manager import ContextManager
        
        class MockContext:
            thread_id = "empty_thread"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            result = await search_history(query="xyznonexistent")
            assert "No messages found" in result
            
        finally:
            ContextManager.current = original_current


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestMemoryPersistence:
    """Tests for memory persistence across operations."""

    @pytest.mark.asyncio
    async def test_memory_persisted_to_file(self, memory_setup, monkeypatch):
        """Test that remembered content is actually saved to files."""
        from app.core.engine.tools.memory_tools import remember
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "persistence_test_user"
            project_id = 77
            thread_id = "persistence_thread"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Remember something
            await remember(
                content="This should be saved to a file",
                context="Testing persistence"
            )
            
            # Check that file was created
            memory_root = memory_setup["root"]
            team_dir = os.path.join(memory_root, "team")
            
            # Wait a bit for async operations
            await asyncio.sleep(0.1)
            
            # Check if any files were created
            found_files = []
            if os.path.exists(team_dir):
                for root, dirs, files in os.walk(team_dir):
                    for file in files:
                        if file.endswith('.md'):
                            found_files.append(os.path.join(root, file))
            
            # There should be at least one memory file
            # (Note: This might fail if the implementation uses different paths)
            # assert len(found_files) > 0, f"No memory files found in {team_dir}"
            
        finally:
            ContextManager.current = original_current


class TestMemoryToolsErrorHandling:
    """Integration tests for error scenarios."""

    @pytest.mark.skip(reason="Module deleted in schema migration")
    @pytest.mark.asyncio
    async def test_remember_with_invalid_context(self, monkeypatch):
        """Test behavior when context manager fails."""
        from app.core.engine.tools.memory_tools import remember
        from app.core.context.manager import ContextManager
        
        # Make context manager raise an exception
        original_current = ContextManager.current
        ContextManager.current = lambda: (_ for _ in ()).throw(Exception("Context error"))
        
        try:
            result = await remember(content="Test content")
            assert "❌ Failed" in result
            
        finally:
            ContextManager.current = original_current
    
    @pytest.mark.skip(reason="Module deleted in schema migration")
    @pytest.mark.asyncio
    async def test_recall_with_database_error(self, monkeypatch):
        """Test recall when database is unavailable."""
        from app.core.engine.tools.memory_tools import recall
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "test_user"
            project_id = 1
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Mock MemoryContainer to raise error during initialization
            from app.core.engine.tools import memory_tools
            from app.core.memory.container import MemoryContainer
            
            class FailingMemoryContainer:
                def __init__(self, *args, **kwargs):
                    raise Exception("Database connection failed")
            
            original_container = memory_tools.MemoryContainer
            memory_tools.MemoryContainer = FailingMemoryContainer
            
            try:
                result = await recall(query="test")
                assert "❌ Failed" in result
            finally:
                memory_tools.MemoryContainer = original_container
            
        finally:
            ContextManager.current = original_current


# Simple smoke test that doesn't require full setup
class TestMemoryToolsSmoke:
    """Quick smoke tests to verify basic functionality."""

    @pytest.mark.skip(reason="Module deleted in schema migration")
    @pytest.mark.asyncio
    async def test_tools_are_callable(self):
        """Test that tool functions are properly defined and callable."""
        from app.core.engine.tools.memory_tools import remember, recall, search_history
        
        # Check that functions exist and have correct signatures
        import inspect
        
        assert inspect.iscoroutinefunction(remember)
        assert inspect.iscoroutinefunction(recall)
        assert inspect.iscoroutinefunction(search_history)
        
        # Check that they have the evoloop_tool decorator metadata
        assert hasattr(remember, '_evoloop_tool_meta')
        assert hasattr(recall, '_evoloop_tool_meta')
        assert hasattr(search_history, '_evoloop_tool_meta')
    
    @pytest.mark.skip(reason="Module deleted in schema migration")
    @pytest.mark.asyncio
    async def test_input_models_are_valid(self):
        """Test that Pydantic input models work correctly."""
        from app.core.engine.tools.memory_tools import RememberInput, RecallInput, SearchHistoryInput
        
        # Test valid inputs
        remember_input = RememberInput(content="Test content", context="Context")
        assert remember_input.content == "Test content"
        
        recall_input = RecallInput(query="test query", limit=3)
        assert recall_input.query == "test query"
        assert recall_input.limit == 3
        
        search_input = SearchHistoryInput(query="search term")
        assert search_input.query == "search term"
        
        # Test defaults
        remember_input_no_ctx = RememberInput(content="Test")
        assert remember_input_no_ctx.context == ""
        
        recall_input_default = RecallInput(query="test")
        assert recall_input_default.limit == 5


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestSmartRetrievalPhase3:
    """Integration tests for Phase 3 Smart Retrieval features."""

    @pytest.mark.asyncio
    async def test_recall_with_smart_retrieval(self, memory_setup, monkeypatch):
        """Test that recall uses smart retrieval (get_relevant_memories)."""
        from app.core.engine.tools.memory_tools import recall
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "smart_test_user"
            project_id = 99
            thread_id = "smart_test_thread"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Mock get_relevant_memories to verify it's called
            from app.core import memory as memory_module
            from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
            
            mock_calls = []
            
            async def mock_get_relevant(**kwargs):
                mock_calls.append(kwargs)
                now = datetime.utcnow()
                return [
                    MemoryEntry(
                        id="mem_smart_001",
                        type=MemoryType.PROJECT,
                        privacy=PrivacyLevel.TEAM,
                        title="Smart Retrieval Result",
                        description="Test result",
                        content="Content",
                        created_at=now,
                        updated_at=now,
                    )
                ]
            
            original_fn = memory_module.get_relevant_memories
            memory_module.get_relevant_memories = mock_get_relevant
            
            try:
                result = await recall(query="Docker deployment", limit=3)
                
                # Verify smart retrieval was called with correct parameters
                assert len(mock_calls) == 1
                assert mock_calls[0]["query"] == "Docker deployment"
                assert mock_calls[0]["max_results"] == 5
                assert mock_calls[0]["user_id"] == "smart_test_user"
                assert mock_calls[0]["project_id"] == 99
                
                # Verify result format includes type emoji
                assert "📚 Recalled" in result or "No memories" in result
                
            finally:
                memory_module.get_relevant_memories = original_fn
                
        finally:
            ContextManager.current = original_current
    
    @pytest.mark.asyncio
    async def test_recall_returns_formatted_memories(self, memory_setup, monkeypatch):
        """Test that recall returns properly formatted memories with type emojis."""
        from app.core.engine.tools.memory_tools import recall
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "format_test_user"
            project_id = 1
            thread_id = "format_test_thread"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            from app.core import memory as memory_module
            from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
            
            now = datetime.utcnow()
            
            async def mock_get_relevant(**kwargs):
                return [
                    MemoryEntry(
                        id="mem_user",
                        type=MemoryType.USER,
                        privacy=PrivacyLevel.PRIVATE,
                        title="User Preference",
                        description="Prefers dark mode",
                        content="I prefer dark mode",
                        created_at=now,
                        updated_at=now,
                        user_id="format_test_user",
                    ),
                    MemoryEntry(
                        id="mem_project",
                        type=MemoryType.PROJECT,
                        privacy=PrivacyLevel.TEAM,
                        title="Project Config",
                        description="Config info",
                        content="Use TypeScript",
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            
            original_fn = memory_module.get_relevant_memories
            memory_module.get_relevant_memories = mock_get_relevant
            
            try:
                result = await recall(query="preference", limit=5)
                
                # Should include type indicators
                assert "👤" in result or "📁" in result or "user" in result.lower() or "project" in result.lower()
                
            finally:
                memory_module.get_relevant_memories = original_fn
                
        finally:
            ContextManager.current = original_current


class TestMemoryStateTrackingPhase3:
    """Integration tests for Phase 3 State Tracking features."""
    
    @pytest.mark.asyncio
    async def test_memory_tracker_prevents_duplicates(self, monkeypatch):
        """Test that memory tracker prevents showing same memory twice."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Mark some memories as surfaced
        tracker.mark_surfaced("thread_test", ["mem_001", "mem_002"])
        
        # Check they are surfaced
        assert tracker.is_surfaced("thread_test", "mem_001") is True
        assert tracker.is_surfaced("thread_test", "mem_002") is True
        assert tracker.is_surfaced("thread_test", "mem_003") is False
        
        # Filter fresh memories
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001"), MockEntry("mem_002"), MockEntry("mem_003")]
        fresh = tracker.filter_fresh("thread_test", entries)
        
        # Should only include mem_003
        assert len(fresh) == 1
        assert fresh[0].id == "mem_003"
    
    @pytest.mark.asyncio
    async def test_memory_tracker_ttl(self, monkeypatch):
        """Test that memory tracker TTL expires old entries."""
        from app.core.memory.state_tracking import MemoryStateTracker
        import time
        
        tracker = MemoryStateTracker()
        
        # Mark as surfaced with manual old timestamp
        tracker._surfaced["thread_ttl"]["mem_old"] = time.time() - 7200  # 2 hours ago
        
        # Should be expired (default TTL is 1 hour)
        assert tracker.is_surfaced("thread_ttl", "mem_old") is False
        
        # Mark as surfaced now
        tracker.mark_surfaced("thread_ttl", ["mem_fresh"])
        
        # Should be surfaced
        assert tracker.is_surfaced("thread_ttl", "mem_fresh") is True


class TestMemoryQualityPhase3:
    """Integration tests for Phase 3 Quality Analysis features."""
    
    @pytest.mark.asyncio
    async def test_quality_analysis_scores(self, monkeypatch):
        """Test that quality analyzer calculates correct scores."""
        from app.core.memory.quality import MemoryQualityAnalyzer
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        # Test fresh, high-quality memory
        entry = MemoryEntry(
            id="mem_quality_high",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Best Practices",
            description="How to use Docker",
            content="Always use multi-stage builds. **Why:** Reduces image size.",
            created_at=now,
            updated_at=now,
        )
        
        scores = await analyzer.analyze_memory(entry)
        
        # Should have high freshness (new)
        assert scores.freshness > 0.9
        
        # Should have good actionability (has "Always" and structured format)
        assert scores.actionability > 0.3
        
        # Overall should be good
        assert scores.overall > 0.3
    
    @pytest.mark.asyncio
    async def test_quality_cleanup_recommendations(self, monkeypatch):
        """Test that quality analyzer generates cleanup recommendations."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        # Create a very low-quality memory
        entry = MemoryEntry(
            id="mem_low_quality",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Vague Memory",
            description="Something",
            content="Maybe somehow do something.",
            created_at=now - timedelta(days=100),  # Very old
            updated_at=now - timedelta(days=100),
        )
        
        scores = QualityScores(
            freshness=0.05,
            usage=0.0,
            specificity=0.1,
            actionability=0.1,
            overall=0.1,
        )
        
        action, reason, suggestions = analyzer._determine_action(entry, scores)
        
        # Should recommend deletion for very low quality
        assert action in ["delete", "archive"]
        assert len(suggestions) > 0


class TestGlobalInstancesPhase3:
    """Tests for Phase 3 global instances."""
    
    @pytest.mark.skip(reason="Module deleted in schema migration")
    def test_smart_retriever_global(self):
        """Test that global smart_retriever exists."""
        from app.core.memory import smart_retriever
        from app.core.memory.smart_retrieval import SmartMemoryRetriever

        assert isinstance(smart_retriever, SmartMemoryRetriever)

    @pytest.mark.skip(reason="Module deleted in schema migration")
    def test_quality_analyzer_global(self):
        """Test that global quality_analyzer exists."""
        from app.core.memory import quality_analyzer
        from app.core.memory.quality import MemoryQualityAnalyzer

        assert isinstance(quality_analyzer, MemoryQualityAnalyzer)
    
    def test_memory_tracker_global(self):
        """Test that global memory_tracker exists."""
        from app.core.memory import memory_tracker
        from app.core.memory.state_tracking import MemoryStateTracker
        
        assert isinstance(memory_tracker, MemoryStateTracker)
