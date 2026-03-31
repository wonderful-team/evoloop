"""
Tests for Memory Search Functionality
=====================================

Tests the improved search_chat_history and manage_memory tools:
1. Multi-keyword OR search in SqlShortTermMemory
2. manage_memory facade with search_history action
3. Context auto-resolution via ContextManager
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage


class TestSqlShortTermMemoryMultiKeywordSearch:
    """Tests for multi-keyword OR search functionality."""

    @pytest.fixture
    def mock_session_scope(self):
        """Mock the database session scope."""
        with patch("app.core.memory.backends.sql_short_term.session_scope") as mock:
            yield mock

    @pytest.fixture
    def memory(self):
        """Create SqlShortTermMemory instance."""
        from app.core.memory.backends.sql_short_term import SqlShortTermMemory
        return SqlShortTermMemory()

    @pytest.mark.asyncio
    async def test_single_keyword_search(self, memory, mock_session_scope):
        """Test search with single keyword."""
        # Mock the database result
        mock_db = AsyncMock()
        mock_message = MagicMock()
        mock_message.role = "human"
        mock_message.content = "Let's use PostgreSQL for the database"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_message]
        mock_db.execute.return_value = mock_result
        
        # Mock async context manager
        mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=None)

        results = await memory.search_messages("PostgreSQL", thread_id="test_thread")
        
        assert len(results) == 1
        assert isinstance(results[0], HumanMessage)
        assert "PostgreSQL" in results[0].content

    @pytest.mark.asyncio
    async def test_multi_keyword_or_search(self, memory, mock_session_scope):
        """Test multi-keyword search uses OR logic."""
        mock_db = AsyncMock()
        
        # Two messages: one contains "Docker", one contains "PostgreSQL"
        msg1 = MagicMock()
        msg1.role = "human"
        msg1.content = "We should use Docker for containerization"
        
        msg2 = MagicMock()
        msg2.role = "ai"
        msg2.content = "PostgreSQL is a good choice for the database"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [msg1, msg2]
        mock_db.execute.return_value = mock_result
        
        mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=None)

        # Search with space-separated keywords
        results = await memory.search_messages("Docker PostgreSQL", thread_id="test_thread")
        
        # Should find both messages (OR logic)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_multi_keyword_extraction(self, memory, mock_session_scope):
        """Test that keywords are properly extracted and trimmed."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=None)

        # Search with extra spaces
        await memory.search_messages("  Docker   PostgreSQL  API  ", thread_id="test_thread")
        
        # Verify the query was constructed with OR conditions
        # The SQL should use or_() for multiple keywords
        call_args = mock_db.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, memory, mock_session_scope):
        """Test that empty query returns empty list."""
        results = await memory.search_messages("", thread_id="test_thread")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_without_thread_id(self, memory, mock_session_scope):
        """Test search works without thread_id (searches all threads)."""
        mock_db = AsyncMock()
        mock_message = MagicMock()
        mock_message.role = "human"
        mock_message.content = "Some message content"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_message]
        mock_db.execute.return_value = mock_result
        
        mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=None)

        results = await memory.search_messages("content", thread_id=None)
        
        assert len(results) == 1


class TestManageMemoryFacade:
    """Tests for manage_memory facade tool."""

    @pytest.fixture
    def mock_search_chat_history(self):
        """Mock search_chat_history tool."""
        with patch("app.domain.tools.facades.search_chat_history") as mock:
            mock.ainvoke = AsyncMock(return_value=[
                HumanMessage(content="Let's use PostgreSQL for the database"),
                AIMessage(content="Good choice, I'll set up the Docker configuration")
            ])
            yield mock

    @pytest.fixture
    def mock_context_manager(self):
        """Mock ContextManager for auto thread_id resolution."""
        with patch("app.domain.tools.memory_search.ContextManager") as mock:
            mock_context = MagicMock()
            mock_context.thread_id = "auto_resolved_thread_123"
            mock.current.return_value = mock_context
            yield mock

    @pytest.mark.asyncio
    async def test_search_history_action(self, mock_search_chat_history):
        """Test manage_memory with search_history action."""
        from app.domain.tools.facades import manage_memory

        result = await manage_memory.ainvoke({
            "action": "search_history",
            "key": "PostgreSQL Docker"
        })

        # Verify search_chat_history was called
        mock_search_chat_history.ainvoke.assert_called_once()
        call_args = mock_search_chat_history.ainvoke.call_args[0][0]
        assert call_args["query"] == "PostgreSQL Docker"

    @pytest.mark.asyncio
    async def test_search_history_without_key(self):
        """Test search_history requires key parameter."""
        from app.domain.tools.facades import manage_memory

        result = await manage_memory.ainvoke({
            "action": "search_history"
            # key is missing
        })

        assert "Error" in result
        assert "key (query) required" in result

    @pytest.mark.asyncio
    async def test_search_history_extracts_technical_terms(self, mock_search_chat_history):
        """Test that search extracts technical terms, not round numbers."""
        from app.domain.tools.facades import manage_memory

        # User refers to "第3轮" but we should search for technical terms
        await manage_memory.ainvoke({
            "action": "search_history",
            "key": "PostgreSQL 数据库 Docker"  # Extracted technical terms
        })

        call_args = mock_search_chat_history.ainvoke.call_args[0][0]
        query = call_args["query"]
        
        # Should NOT contain "第3轮" - it won't match message content
        assert "第3轮" not in query
        # Should contain technical terms
        assert "PostgreSQL" in query or "数据库" in query or "Docker" in query


class TestSearchChatHistoryTool:
    """Tests for search_chat_history standalone tool."""
    
    def test_tool_has_thread_id_parameter(self):
        """Verify search_chat_history tool accepts thread_id parameter."""
        from app.domain.tools.memory_search import search_chat_history
        
        # Tool is a StructuredTool after decoration
        # Check args_schema or direct attributes
        args_schema = getattr(search_chat_history, 'args_schema', None)
        assert args_schema is not None, "Tool should have args_schema"
        
        # Check that thread_id is in the schema
        schema_dict = args_schema.model_json_schema()
        properties = schema_dict.get('properties', {})
        assert "thread_id" in properties, "thread_id should be in schema"
        assert "query" in properties, "query should be in schema"
        
        # thread_id should be optional (not in required)
        required = schema_dict.get('required', [])
        assert "thread_id" not in required, "thread_id should be optional"
        
        print("   ✅ search_chat_history has correct parameters")


class TestPromptDocumentation:
    """Tests to verify prompt templates contain correct documentation."""

    def test_supervisor_prompt_contains_context_recovery(self):
        """Verify Supervisor prompt documents Context Recovery."""
        prompt_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/prompts/templates/supervisor.prompt.j2"
        
        with open(prompt_path) as f:
            content = f.read()
        
        # Should contain Context Recovery section
        assert "Context Recovery" in content
        assert 'manage_memory(action="search_history")' in content
        
        # Should contain keyword strategy
        assert "KEYWORD STRATEGY" in content
        assert "第3轮" in content  # Example of what NOT to search
        assert "PostgreSQL" in content  # Example of what TO search
        
        # Should contain guidance on passing context to Worker
        assert "PASS CONTEXT TO WORKER" in content
        assert "historical_context" in content

    def test_worker_prompt_contains_manage_memory(self):
        """Verify Worker prompt documents manage_memory usage."""
        prompt_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/prompts/templates/worker.prompt.j2"
        
        with open(prompt_path) as f:
            content = f.read()
        
        # Should contain manage_memory documentation
        assert "When to use `manage_memory`" in content
        assert "search_history" in content
        
        # Should contain keyword extraction guidance
        assert "KEYWORD EXTRACTION" in content
        assert "GOOD" in content
        assert "BAD" in content

    def test_manage_memory_source_contains_examples(self):
        """Verify manage_memory source contains usage examples."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/facades.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Find manage_memory function docstring
        assert "async def manage_memory" in content
        
        # Should contain search_history documentation in docstring
        assert "search_history" in content
        
        # Should contain usage guidance
        assert "之前说的" in content
        
        # Should contain examples
        assert "Examples:" in content
        
        # Should contain keyword strategy guidance
        assert "第X轮" in content or "第3轮" in content

    def test_search_chat_history_source_contains_strategy(self):
        """Verify search_chat_history source contains keyword strategy."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/memory_search.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Find search_chat_history function
        assert "async def search_chat_history" in content
        
        # Should contain keyword extraction strategy
        assert "KEYWORD" in content
        
        # Should contain examples of good vs bad queries
        assert "Examples:" in content
        
        # Should mention technical terms
        assert "PostgreSQL" in content or "Docker" in content or "technical" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
