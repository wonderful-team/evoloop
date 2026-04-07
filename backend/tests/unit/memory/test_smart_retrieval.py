"""
Unit tests for Smart Memory Retrieval (Phase 3).

Tests two-stage retrieval, LLM-assisted selection, and filtering.

Run with: pytest tests/unit/memory/test_smart_retrieval.py -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, Mock


class TestSmartMemoryRetrieverInit:
    """Tests for SmartMemoryRetriever initialization."""
    
    def test_default_initialization(self):
        """Test that retriever initializes with defaults."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        
        retriever = SmartMemoryRetriever()
        
        assert retriever.max_candidates == 20
        assert retriever.max_results == 5
        assert retriever.enable_llm_selection is True
    
    def test_custom_initialization(self):
        """Test that retriever accepts custom configuration."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        
        retriever = SmartMemoryRetriever(
            max_candidates=50,
            max_results=10,
            enable_llm_selection=False,
        )
        
        assert retriever.max_candidates == 50
        assert retriever.max_results == 10
        assert retriever.enable_llm_selection is False


class TestCandidateScoring:
    """Tests for candidate scoring logic."""
    
    def test_basic_keyword_scoring(self):
        """Test that keyword matches increase score."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Best Practices",
            description="How to use Docker effectively",
            content="Always use multi-stage builds",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        ctx = RetrievalContext(
            query="Docker best practices",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        score = retriever._score_candidate(entry, ctx)
        
        # Should have positive score for keyword matches
        assert score > 0
    
    def test_title_keyword_boost(self):
        """Test that title matches are weighted higher."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        
        # Entry with keyword in title
        entry_with_title = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Deployment Guide",
            description="Some other content",
            content="More content",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        # Entry with keyword only in content
        entry_without_title = MemoryEntry(
            id="mem_002",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Some Guide",
            description="Docker deployment info",
            content="Docker content here",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        ctx = RetrievalContext(
            query="Docker",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        score_with_title = retriever._score_candidate(entry_with_title, ctx)
        score_without_title = retriever._score_candidate(entry_without_title, ctx)
        
        # Title match should score higher
        assert score_with_title > score_without_title
    
    def test_freshness_boost(self):
        """Test that recent memories get freshness boost."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        
        now = datetime.utcnow()
        
        # Recent entry
        recent_entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Recent Memory",
            description="Just created",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        # Old entry
        old_entry = MemoryEntry(
            id="mem_002",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Old Memory",
            description="Very old",
            content="Content",
            created_at=now - timedelta(days=60),
            updated_at=now - timedelta(days=60),
        )
        
        ctx = RetrievalContext(
            query="memory",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        recent_score = retriever._score_candidate(recent_entry, ctx)
        old_score = retriever._score_candidate(old_entry, ctx)
        
        # Recent entry should score higher due to freshness
        assert recent_score > old_score
    
    def test_type_priority_multiplier(self):
        """Test that different types have priority multipliers."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Create entries with same content but different types
        base_kwargs = {
            "privacy": PrivacyLevel.PRIVATE,
            "title": "Test",
            "description": "Test desc",
            "content": "Test content",
            "created_at": now,
            "updated_at": now,
        }
        
        user_entry = MemoryEntry(id="mem_user", type=MemoryType.USER, **base_kwargs)
        feedback_entry = MemoryEntry(id="mem_feedback", type=MemoryType.FEEDBACK, **base_kwargs)
        project_entry = MemoryEntry(id="mem_project", type=MemoryType.PROJECT, **base_kwargs)
        reference_entry = MemoryEntry(id="mem_reference", type=MemoryType.REFERENCE, **base_kwargs)
        
        ctx = RetrievalContext(
            query="test",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        user_score = retriever._score_candidate(user_entry, ctx)
        feedback_score = retriever._score_candidate(feedback_entry, ctx)
        project_score = retriever._score_candidate(project_entry, ctx)
        reference_score = retriever._score_candidate(reference_entry, ctx)
        
        # User should score highest, reference lowest
        assert user_score > feedback_score
        assert feedback_score > project_score
        assert project_score > reference_score


class TestRecentToolFiltering:
    """Tests for filtering memories about recently used tools."""
    
    def test_filter_recent_tools(self):
        """Test that memories about recent tools are filtered out."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Memory about Docker (recently used - contains "docker")
        docker_memory = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Configuration",
            description="How to configure Docker containers",
            content="Use docker-compose for orchestration with docker",
            created_at=now,
            updated_at=now,
        )
        
        # Memory about Kubernetes (not recently used)
        k8s_memory = MemoryEntry(
            id="mem_002",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Kubernetes Guide",
            description="Kubernetes deployment patterns",
            content="Use helm charts for deployment",
            created_at=now,
            updated_at=now,
        )
        
        candidates = [docker_memory, k8s_memory]
        # "docker" is in the recent_tools list and appears in docker_memory content
        recent_tools = ["docker", "docker_compose"]
        
        filtered = retriever._filter_recent_tools(candidates, recent_tools)
        
        # Should filter out Docker memory but keep Kubernetes
        assert len(filtered) == 1
        assert filtered[0].id == "mem_002"
    
    def test_keep_warnings_despite_recent_tools(self):
        """Test that memories with warnings are kept even for recent tools."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Memory with warning about Docker
        warning_memory = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Warning",
            description="Important caution about Docker",
            content="Warning: Don't use docker-compose in production without proper security",
            created_at=now,
            updated_at=now,
        )
        
        candidates = [warning_memory]
        recent_tools = ["docker"]
        
        filtered = retriever._filter_recent_tools(candidates, recent_tools)
        
        # Should keep the warning even though Docker is recent
        assert len(filtered) == 1
        assert filtered[0].id == "mem_001"
    
    def test_no_filtering_without_recent_tools(self):
        """Test that all memories pass through when no recent tools."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        entries = [
            MemoryEntry(
                id=f"mem_{i}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Memory {i}",
                description="Description",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            for i in range(3)
        ]
        
        filtered = retriever._filter_recent_tools(entries, [])
        
        # All should pass through
        assert len(filtered) == 3


class TestLLMResponseParsing:
    """Tests for parsing LLM selection responses."""
    
    def test_parse_valid_json_response(self):
        """Test parsing valid JSON selection response."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="A", description="D", content="C", created_at=now, updated_at=now),
            MemoryEntry(id="mem_002", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="B", description="D", content="C", created_at=now, updated_at=now),
            MemoryEntry(id="mem_003", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="C", description="D", content="C", created_at=now, updated_at=now),
        ]
        
        response = '{"selected_indices": [1, 3], "reasoning": "Selected A and C"}'
        
        selected_ids = retriever._parse_selection_response(response, candidates)
        
        assert len(selected_ids) == 2
        assert "mem_001" in selected_ids
        assert "mem_003" in selected_ids
    
    def test_parse_json_in_code_block(self):
        """Test parsing JSON inside markdown code block."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="A", description="D", content="C", created_at=now, updated_at=now),
        ]
        
        response = '''```json
{"selected_indices": [1], "reasoning": "Good match"}
```'''
        
        selected_ids = retriever._parse_selection_response(response, candidates)
        
        assert len(selected_ids) == 1
        assert "mem_001" in selected_ids
    
    def test_parse_empty_selection(self):
        """Test parsing empty selection response."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="A", description="D", content="C", created_at=now, updated_at=now),
        ]
        
        response = '{"selected_indices": [], "reasoning": "No relevant memories"}'
        
        selected_ids = retriever._parse_selection_response(response, candidates)
        
        assert len(selected_ids) == 0
    
    def test_parse_invalid_json_fallback(self):
        """Test that invalid JSON falls back to first N candidates."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever(max_results=2)
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="A", description="D", content="C", created_at=now, updated_at=now),
            MemoryEntry(id="mem_002", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="B", description="D", content="C", created_at=now, updated_at=now),
            MemoryEntry(id="mem_003", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="C", description="D", content="C", created_at=now, updated_at=now),
        ]
        
        response = "This is not valid JSON"
        
        selected_ids = retriever._parse_selection_response(response, candidates)
        
        # Should fallback to first max_results entries
        assert len(selected_ids) == 2
        assert "mem_001" in selected_ids
        assert "mem_002" in selected_ids


class TestKeywordRanking:
    """Tests for keyword-based ranking fallback."""
    
    def test_keyword_rank_basic(self):
        """Test basic keyword ranking."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        entries = [
            MemoryEntry(
                id="mem_001",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Docker Guide",
                description="Docker content",
                content="Docker stuff",
                created_at=now,
                updated_at=now,
            ),
            MemoryEntry(
                id="mem_002",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Kubernetes Guide",
                description="Kubernetes content",
                content="K8s stuff",
                created_at=now,
                updated_at=now,
            ),
        ]
        
        ctx = RetrievalContext(
            query="Docker",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        ranked = retriever._keyword_rank(entries, ctx)
        
        # Docker entry should be first
        assert ranked[0].id == "mem_001"
    
    def test_keyword_rank_with_freshness(self):
        """Test that keyword ranking considers freshness."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        entries = [
            MemoryEntry(
                id="mem_001",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Docker Guide",
                description="Docker content",
                content="Docker stuff",
                created_at=now - timedelta(days=60),
                updated_at=now - timedelta(days=60),
            ),
            MemoryEntry(
                id="mem_002",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Docker Tips",
                description="Docker content",
                content="Docker stuff",
                created_at=now,
                updated_at=now,
            ),
        ]
        
        ctx = RetrievalContext(
            query="Docker",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        ranked = retriever._keyword_rank(entries, ctx)
        
        # More recent entry should rank higher (same keyword match, better freshness)
        assert ranked[0].id == "mem_002"


class TestSelectionPromptBuilding:
    """Tests for the LLM selection prompt."""
    
    def test_prompt_includes_query(self):
        """Test that prompt includes the query."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="Test", description="Desc", content="Content",
                       created_at=now, updated_at=now),
        ]
        
        ctx = RetrievalContext(
            query="How do I deploy?",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        prompt = retriever._build_selection_prompt(candidates, ctx)
        
        assert "How do I deploy?" in prompt
    
    def test_prompt_includes_memories(self):
        """Test that prompt includes memory descriptions."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="Docker Guide", description="Docker deployment info",
                       content="Content", created_at=now, updated_at=now),
        ]
        
        ctx = RetrievalContext(
            query="test",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        prompt = retriever._build_selection_prompt(candidates, ctx)
        
        assert "Docker Guide" in prompt
        assert "project" in prompt.lower()
    
    def test_prompt_includes_recent_tools_warning(self):
        """Test that prompt warns about recent tools."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        candidates = [
            MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                       title="Test", description="Desc", content="Content",
                       created_at=now, updated_at=now),
        ]
        
        ctx = RetrievalContext(
            query="test",
            recent_tools=["docker_build", "deploy"],
            already_surfaced=set(),
        )
        
        prompt = retriever._build_selection_prompt(candidates, ctx)
        
        assert "docker_build" in prompt
        assert "deploy" in prompt
        assert "Recently used tools" in prompt


class TestGlobalInstances:
    """Tests for global singleton instances."""
    
    def test_smart_retriever_singleton(self):
        """Test that global smart_retriever exists."""
        from app.core.memory.smart_retrieval import smart_retriever
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        
        assert isinstance(smart_retriever, SmartMemoryRetriever)
    
    def test_get_relevant_memories_function(self):
        """Test that get_relevant_memories convenience function exists."""
        from app.core.memory.smart_retrieval import get_relevant_memories
        
        import inspect
        assert inspect.iscoroutinefunction(get_relevant_memories)
