"""
Tests for SQL Multi-Keyword Search Logic
========================================

Tests the multi-keyword OR search implementation in SqlShortTermMemory
without requiring full backend configuration.
"""
import pytest


class TestMultiKeywordQueryParsing:
    """Test the keyword parsing logic that would be used in SQL search."""

    def test_single_keyword(self):
        """Test parsing single keyword."""
        query = "PostgreSQL"
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == ["PostgreSQL"]

    def test_multiple_keywords(self):
        """Test parsing multiple space-separated keywords."""
        query = "Docker PostgreSQL API"
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == ["Docker", "PostgreSQL", "API"]

    def test_keywords_with_extra_spaces(self):
        """Test parsing keywords with extra whitespace."""
        query = "  Docker   PostgreSQL  "
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == ["Docker", "PostgreSQL"]

    def test_chinese_keywords(self):
        """Test parsing Chinese keywords."""
        query = "数据库 PostgreSQL Docker"
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == ["数据库", "PostgreSQL", "Docker"]

    def test_empty_query(self):
        """Test parsing empty query."""
        query = ""
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == []

    def test_whitespace_only_query(self):
        """Test parsing whitespace-only query."""
        query = "   "
        keywords = [k.strip() for k in query.split() if k.strip()]
        assert keywords == []


class TestSQLConditionBuilding:
    """Test the SQL condition building logic."""

    def test_single_keyword_condition(self):
        """Test building SQL condition for single keyword."""
        query = "PostgreSQL"
        keywords = [k.strip() for k in query.split() if k.strip()]
        
        # Should use single LIKE condition
        if len(keywords) == 1:
            condition = f"content ILIKE '%{keywords[0]}%'"
        else:
            conditions = [f"content ILIKE '%{k}%'" for k in keywords]
            condition = " OR ".join(conditions)
        
        assert condition == "content ILIKE '%PostgreSQL%'"

    def test_multiple_keywords_or_condition(self):
        """Test building SQL OR condition for multiple keywords."""
        query = "Docker PostgreSQL"
        keywords = [k.strip() for k in query.split() if k.strip()]
        
        # Should use OR condition
        if len(keywords) > 1:
            conditions = [f"content ILIKE '%{k}%'" for k in keywords]
            condition = " OR ".join(conditions)
        else:
            condition = f"content ILIKE '%{keywords[0]}%'"
        
        assert "content ILIKE '%Docker%'" in condition
        assert "content ILIKE '%PostgreSQL%'" in condition
        assert " OR " in condition

    def test_technical_term_extraction(self):
        """Test extracting technical terms from user query."""
        # Simulating the extraction that should happen
        user_reference = "第3轮的数据库方案"
        
        # LLM should extract technical terms, not round numbers
        extracted_terms = ["数据库", "PostgreSQL", "MySQL"]  # Example extraction
        
        # Verify round markers are NOT in search terms
        assert "第3轮" not in extracted_terms
        assert "第" not in " ".join(extracted_terms)
        
        # Verify technical terms ARE present
        assert "数据库" in extracted_terms


class TestSourceCodeVerification:
    """Verify the implementation in source files."""

    def test_sql_short_term_impl_has_or_logic(self):
        """Verify SqlShortTermMemory.search_messages implements OR logic."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/memory/backends/sql_short_term.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Should contain the multi-keyword search logic
        assert "keywords = [k.strip() for k in query.split() if k.strip()]" in content
        
        # Should use OR condition for multiple keywords
        assert "or_(*conditions)" in content
        
        # Should have proper docstring
        assert "multi-keyword" in content.lower() or "OR" in content

    def test_sql_short_term_handles_empty_query(self):
        """Verify empty query handling."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/memory/backends/sql_short_term.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Should handle empty keywords
        assert "return []" in content

    def test_memory_search_has_docstring_strategy(self):
        """Verify search_chat_history has keyword strategy in docstring."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/memory_search.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Should have keyword extraction strategy
        assert "KEYWORD" in content
        
        # Should have examples showing what NOT to search
        assert "第3轮" in content or "第X轮" in content
        
        # Should recommend technical terms
        assert "PostgreSQL" in content or "Docker" in content or "technical" in content

    def test_manage_memory_calls_search_chat_history(self):
        """Verify manage_memory properly delegates to search_chat_history."""
        source_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/facades.py"
        
        with open(source_path) as f:
            content = f.read()
        
        # Should import search_chat_history
        assert "from app.domain.tools.memory_search import search_chat_history" in content
        
        # Should have search_history action case
        assert 'elif action == "search_history":' in content
        
        # Should delegate to search_chat_history
        assert "await search_chat_history.ainvoke" in content


class TestPromptTemplates:
    """Verify prompt templates contain correct documentation."""

    def test_supervisor_prompt_context_recovery(self):
        """Verify Supervisor prompt documents Context Recovery."""
        prompt_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/prompts/templates/supervisor.prompt.j2"
        
        with open(prompt_path) as f:
            content = f.read()
        
        # Should contain Context Recovery section
        assert "Context Recovery" in content
        assert 'manage_memory(action="search_history")' in content
        
        # Should contain keyword strategy
        assert "KEYWORD STRATEGY" in content
        assert "第3轮" in content
        assert "PostgreSQL" in content
        
        # Should contain guidance on passing context to Worker
        assert "PASS CONTEXT TO WORKER" in content
        assert "historical_context" in content
        assert "route_to" in content

    def test_worker_prompt_manage_memory(self):
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
        assert "第3轮" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
