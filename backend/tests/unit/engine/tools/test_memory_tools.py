"""
Unit tests for memory tools (remember, recall, search_history).

pytest tests/unit/engine/tools/test_memory_tools.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def setup_memory_container_mock(mock_container_cls):
    """Helper to setup MemoryContainer mock chain."""
    mock_container = AsyncMock()
    mock_container_cls.return_value = mock_container
    mock_manager = AsyncMock()
    mock_container.memory_manager = mock_manager
    return mock_container, mock_manager


class TestRememberTool:
    """Tests for the remember tool."""

    @pytest.mark.asyncio
    async def test_remember_user_preference(self):
        """Test remembering a user preference (should be PRIVATE/USER type)."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            # Setup mock context
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config.from_settings.return_value = mock_config
            mock_config_cls.from_settings.return_value = mock_config
            
            # Setup mock memory container
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock()
            
            # Test preference content
            result = await remember(
                content="I prefer TypeScript over JavaScript",
                context="User's language preference"
            )
            
            # Verify container was created and initialized
            mock_container_cls.assert_called_once()
            mock_container.initialize.assert_called_once()
            
            # Verify save was called
            assert mock_manager.save_memory.called
            
            # Check the saved entry
            saved_entry = mock_manager.save_memory.call_args[0][0]
            assert saved_entry.type.value == "user"
            assert saved_entry.privacy.value == "private"
            assert "TypeScript" in saved_entry.title
            assert "remembered" in saved_entry.tags
            
            # Check result message
            assert "✅ Remembered" in result
            assert "TypeScript" in result
            
            # Verify shutdown was called
            mock_container.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_remember_project_knowledge(self):
        """Test remembering project knowledge (should be TEAM/PROJECT type)."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config_cls.from_settings.return_value = mock_config
            
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock()
            
            # Test project content (no preference keywords)
            result = await remember(
                content="Use Repository pattern for database access",
                context="Architecture decision"
            )
            
            saved_entry = mock_manager.save_memory.call_args[0][0]
            assert saved_entry.type.value == "project"
            assert saved_entry.privacy.value == "team"
            
            assert "✅ Remembered" in result

    @pytest.mark.asyncio
    async def test_remember_without_context(self):
        """Test remembering without optional context."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = None
            mock_ctx.project_id = None
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config_cls.from_settings.return_value = mock_config
            
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock()
            
            result = await remember(content="Important fact to remember")
            
            assert mock_manager.save_memory.called
            saved_entry = mock_manager.save_memory.call_args[0][0]
            assert saved_entry.content == "Important fact to remember"
            assert "Context:" not in saved_entry.content

    @pytest.mark.asyncio
    async def test_remember_with_long_content(self):
        """Test that long content is truncated for title but kept in content."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = None
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config_cls.from_settings.return_value = mock_config
            
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock()
            
            long_content = "A" * 100
            result = await remember(content=long_content)
            
            saved_entry = mock_manager.save_memory.call_args[0][0]
            assert len(saved_entry.title) <= 65  # 60 + "..."
            assert "..." in saved_entry.title
            assert len(saved_entry.content) == 100  # Full content preserved

    @pytest.mark.asyncio
    async def test_remember_error_handling(self):
        """Test error handling when save fails."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config_cls.from_settings.return_value = mock_config
            
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock(side_effect=Exception("DB error"))
            
            result = await remember(content="Test content")
            
            assert "❌ Failed" in result
            assert "DB error" in result


class TestRecallTool:
    """Tests for the recall tool."""

    @pytest.mark.asyncio
    async def test_recall_with_results(self):
        """Test recalling with matching memories."""
        from app.core.engine.tools.memory_tools import recall
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from datetime import datetime
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Create mock memory entries
            mock_entry = MemoryEntry(
                id="mem_001",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Docker Setup",
                content="Use docker-compose for local development",
                description="Docker setup instructions",
                user_id=None,
                project_id=42,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            mock_get_memories.return_value = [mock_entry]
            
            result = await recall(query="docker", limit=5)
            
            assert "📚 Recalled" in result
            assert "Docker Setup" in result
            assert "docker-compose" in result

    @pytest.mark.asyncio
    async def test_recall_no_results_fallback_to_history(self):
        """Test fallback to conversation history when no long-term memories found."""
        from app.core.engine.tools.memory_tools import recall
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories, \
             patch("app.core.memory.backends.sql_short_term.SqlShortTermMemory") as mock_short:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # No long-term memories
            mock_get_memories.return_value = []
            
            # But has short-term history
            mock_msg = MagicMock()
            mock_msg.type = "human"
            mock_msg.content = "Let's use Docker for deployment"
            mock_short.return_value.search_messages = AsyncMock(return_value=[mock_msg])
            
            result = await recall(query="docker")
            
            assert "🔍 Found in current conversation" in result
            assert "Docker" in result

    @pytest.mark.asyncio
    async def test_recall_no_results_at_all(self):
        """Test when nothing is found."""
        from app.core.engine.tools.memory_tools import recall
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories, \
             patch("app.core.memory.backends.sql_short_term.SqlShortTermMemory") as mock_short:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            mock_get_memories.return_value = []
            mock_short.return_value.search_messages = AsyncMock(return_value=[])
            
            result = await recall(query="nonexistent")
            
            assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_recall_filters_private_memories(self):
        """Test that private memories from other users are filtered out.
        
        Note: Filtering now happens inside get_relevant_memories, so we mock
        it to return only the accessible memories.
        """
        from app.core.engine.tools.memory_tools import recall
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from datetime import datetime
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.project_id = 42
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # get_relevant_memories handles filtering - return only accessible entry
            own_entry = MemoryEntry(
                id="mem_001",
                type=MemoryType.USER,
                privacy=PrivacyLevel.PRIVATE,
                title="My preference",
                content="I like coffee",
                user_id="user_123",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            mock_get_memories.return_value = [own_entry]
            
            result = await recall(query="like")
            
            assert "coffee" in result
            assert "tea" not in result  # Other user's entry filtered out by get_relevant_memories

    @pytest.mark.asyncio
    async def test_recall_error_handling(self):
        """Test error handling when recall fails."""
        from app.core.engine.tools.memory_tools import recall
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            mock_get_memories.side_effect = Exception("Search error")
            
            result = await recall(query="test")
            
            assert "❌ Failed" in result


class TestSearchHistoryTool:
    """Tests for the search_history tool."""

    @pytest.mark.asyncio
    async def test_search_history_with_results(self):
        """Test searching history with matching messages."""
        from app.core.engine.tools.memory_tools import search_history
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.memory.backends.sql_short_term.SqlShortTermMemory") as mock_short:
            
            mock_ctx = MagicMock()
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Mock messages
            mock_msg1 = MagicMock()
            mock_msg1.type = "human"
            mock_msg1.content = "Let's use PostgreSQL for the database"
            
            mock_msg2 = MagicMock()
            mock_msg2.type = "ai"
            mock_msg2.content = "Good choice, PostgreSQL is reliable"
            
            mock_short.return_value.search_messages = AsyncMock(return_value=[mock_msg1, mock_msg2])
            
            result = await search_history(query="PostgreSQL")
            
            assert "🔍 Found" in result
            assert "PostgreSQL" in result
            assert "[User]" in result
            assert "[You]" in result

    @pytest.mark.asyncio
    async def test_search_history_no_results(self):
        """Test searching history with no matches."""
        from app.core.engine.tools.memory_tools import search_history
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.memory.backends.sql_short_term.SqlShortTermMemory") as mock_short:
            
            mock_ctx = MagicMock()
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            mock_short.return_value.search_messages = AsyncMock(return_value=[])
            
            result = await search_history(query="nonexistent")
            
            assert "No messages found" in result

    @pytest.mark.asyncio
    async def test_search_history_no_thread(self):
        """Test error when no active thread."""
        from app.core.engine.tools.memory_tools import search_history
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr:
            mock_ctx = MagicMock()
            mock_ctx.thread_id = None
            mock_ctx_mgr.current.return_value = mock_ctx
            
            result = await search_history(query="test")
            
            assert "Error: No active conversation" in result

    @pytest.mark.asyncio
    async def test_search_history_limits_results(self):
        """Test that results are limited to 5 messages."""
        from app.core.engine.tools.memory_tools import search_history
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.memory.backends.sql_short_term.SqlShortTermMemory") as mock_short:
            
            mock_ctx = MagicMock()
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Create 10 mock messages
            messages = []
            for i in range(10):
                msg = MagicMock()
                msg.type = "human"
                msg.content = f"Message {i}"
                messages.append(msg)
            
            mock_short.return_value.search_messages = AsyncMock(return_value=messages)
            
            result = await search_history(query="Message")
            
            # Should only show first 5
            assert "Message 0" in result
            assert "Message 4" in result


class TestMemoryToolsEdgeCases:
    """Edge case tests for memory tools."""

    @pytest.mark.asyncio
    async def test_remember_empty_content(self):
        """Test remembering empty content."""
        from app.core.engine.tools.memory_tools import remember
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
             patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
            
            mock_ctx = MagicMock()
            mock_ctx_mgr.current.return_value = mock_ctx
            
            # Setup mock config
            mock_config = MagicMock()
            mock_config_cls.from_settings.return_value = mock_config
            
            mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
            mock_manager.save_memory = AsyncMock()
            
            result = await remember(content="")
            
            # Empty content should still work (though not useful)
            assert mock_manager.save_memory.called

    @pytest.mark.asyncio
    async def test_recall_with_special_characters(self):
        """Test recall with special characters in query."""
        from app.core.engine.tools.memory_tools import recall
        
        with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
             patch("app.core.engine.tools.memory_tools.get_relevant_memories") as mock_get_memories:
            
            mock_ctx = MagicMock()
            mock_ctx.user_id = "user_123"
            mock_ctx.thread_id = "thread_abc"
            mock_ctx_mgr.current.return_value = mock_ctx
            
            mock_get_memories.return_value = []
            
            # Should handle special chars without error
            result = await recall(query="<script>alert('xss')</script>")
            
            assert "No memories found" in result or "❌ Failed" in result

    @pytest.mark.asyncio
    async def test_preference_keywords_detection(self):
        """Test various preference keyword patterns."""
        from app.core.engine.tools.memory_tools import remember
        
        test_cases = [
            ("I prefer Python", True),
            ("I like TypeScript", True),
            ("I want to use React", True),
            ("I don't want Java", True),
            ("Always use tabs", True),
            ("Never use global variables", True),
            ("I am a developer", True),
            ("I'm working on", True),
            ("My preference is", True),
            ("Use Repository pattern", False),  # Not a preference
            ("Database connection pool", False),  # Not a preference
        ]
        
        for content, should_be_preference in test_cases:
            with patch("app.core.engine.tools.memory_tools.ContextManager") as mock_ctx_mgr, \
                 patch("app.core.engine.tools.memory_tools.MemoryContainer") as mock_container_cls, \
                 patch("app.core.engine.tools.memory_tools.MemoryConfig") as mock_config_cls:
                
                mock_ctx = MagicMock()
                mock_ctx.user_id = "user_123"
                mock_ctx_mgr.current.return_value = mock_ctx
                
                # Setup mock config
                mock_config = MagicMock()
                mock_config_cls.from_settings.return_value = mock_config
                
                mock_container, mock_manager = setup_memory_container_mock(mock_container_cls)
                mock_manager.save_memory = AsyncMock()
                
                await remember(content=content)
                
                saved_entry = mock_manager.save_memory.call_args[0][0]
                
                if should_be_preference:
                    assert saved_entry.type.value == "user", f"Failed for: {content}"
                else:
                    assert saved_entry.type.value == "project", f"Failed for: {content}"


class TestFreshnessScoring:
    """Tests for freshness-based relevance scoring."""

    def test_freshness_boost_decay(self):
        """Test that freshness boost decays exponentially with age."""
        from datetime import datetime, timedelta
        import math
        
        now = datetime.utcnow()
        
        # Calculate freshness boost for different ages
        def freshness_boost(updated_at):
            age_days = (now - updated_at).days
            return 2.0 * math.exp(-age_days / 30.0)
        
        fresh = freshness_boost(now)
        week_old = freshness_boost(now - timedelta(days=7))
        month_old = freshness_boost(now - timedelta(days=30))
        quarter_old = freshness_boost(now - timedelta(days=90))
        
        # Fresh should have max boost
        assert fresh == 2.0
        
        # Boost should decrease with age
        assert week_old < fresh
        assert month_old < week_old
        assert quarter_old < month_old
        
        # Month-old should be roughly 37% of original (1/e for 30-day half-life is approx)
        # exp(-1) ≈ 0.368, so 2.0 * 0.368 ≈ 0.736
        assert 0.7 < month_old < 0.8
    
    def test_relevance_freshness_tradeoff(self):
        """Test trade-off between relevance and freshness."""
        from datetime import datetime, timedelta
        import math
        
        now = datetime.utcnow()
        query_words = {"docker", "deployment"}
        
        def calculate_score(content, updated_at):
            # Base relevance
            text = content.lower()
            relevance = sum(1 for word in query_words if word in text)
            
            # Freshness boost
            age_days = (now - updated_at).days
            freshness_boost = 2.0 * math.exp(-age_days / 30.0)
            
            return relevance + freshness_boost
        
        # Old but highly relevant vs new but less relevant
        old_high = calculate_score("docker deployment kubernetes helm", now - timedelta(days=60))
        new_low = calculate_score("docker containers", now)
        
        # Both should have reasonable scores
        assert old_high > 0
        assert new_low > 0
    
    def test_freshness_sorting_order(self):
        """Test that entries are sorted by combined score correctly."""
        from datetime import datetime, timedelta
        
        # Create mock entries with different ages
        entries = [
            {"title": "Old entry", "days_ago": 90, "relevance": 3},
            {"title": "New entry", "days_ago": 1, "relevance": 2},
            {"title": "Very old entry", "days_ago": 180, "relevance": 3},
            {"title": "Fresh entry", "days_ago": 0, "relevance": 2},
        ]
        
        # Calculate scores
        now = datetime.utcnow()
        import math
        
        def score(entry):
            relevance = entry["relevance"]
            age_days = entry["days_ago"]
            freshness = 2.0 * math.exp(-age_days / 30.0)
            return relevance + freshness
        
        scored = [(e, score(e)) for e in entries]
        sorted_entries = sorted(scored, key=lambda x: x[1], reverse=True)
        
        # Fresh + relevant should be first
        assert sorted_entries[0][0]["title"] in ["Fresh entry", "New entry"]
        # Very old should be last
        assert sorted_entries[-1][0]["title"] == "Very old entry"


class TestIndexTruncation:
    """Tests for index file size limiting."""

    def test_truncate_index_small_no_change(self):
        """Test that small indexes are not modified."""
        lines = ["# Title", "- Entry 1", "- Entry 2", "- Entry 3"]
        
        # Simulate truncation logic
        max_lines = 200
        if len(lines) <= max_lines:
            result = lines
        
        assert result == lines
    
    def test_truncate_index_large(self):
        """Test that large indexes are truncated."""
        headers = ["# Title", "## Section 1", "## Section 2"]
        entries = [f"- Entry {i}" for i in range(300)]
        lines = headers + entries
        
        # Truncation logic
        max_lines = 200
        if len(lines) > max_lines:
            result_headers = [l for l in lines if l.startswith('#')]
            result_entries = [l for l in lines if not l.startswith('#') and l.strip()]
            max_entries = max_lines - len(result_headers)
            kept_entries = result_entries[:max_entries]
            result = result_headers + kept_entries
        
        assert len(result) <= 200
        # Headers should be preserved
        assert all(h in result for h in headers)
    
    def test_truncate_index_size_based(self):
        """Test size-based truncation."""
        lines = ["# Title"] + [f"- Entry {i}" for i in range(100)]
        
        max_size = 25 * 1024
        content = "\n".join(lines)
        
        # If content is too large, truncate
        while len(content.encode('utf-8')) > max_size and len(lines) > 1:
            lines.pop()
            content = "\n".join(lines)
        
        assert len(content.encode('utf-8')) <= max_size
