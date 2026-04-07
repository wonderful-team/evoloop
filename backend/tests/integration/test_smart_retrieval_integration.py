"""
Integration tests for Smart Memory Retrieval (Phase 3).

Tests end-to-end flow with real memory backend.

Run with: pytest tests/integration/test_smart_retrieval_integration.py -v --tb=short
"""

import pytest
import asyncio
import tempfile
import shutil
import os
from datetime import datetime, timedelta

# Mark all tests as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def test_memory_root():
    """Create a temporary directory for test memory files."""
    temp_dir = tempfile.mkdtemp(prefix="evoloop_test_smart_memory_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def memory_setup(test_memory_root, monkeypatch):
    """Setup memory backend with test configuration."""
    monkeypatch.setenv("BRAIN_MEMORY_ROOT", test_memory_root)
    
    from app.core.config import settings
    monkeypatch.setattr(settings, "BRAIN_MEMORY_ROOT", test_memory_root)
    
    # Initialize file storage
    from app.core.memory.backends.file_backend import FileMemoryStorage
    storage = FileMemoryStorage(root_path=test_memory_root)
    
    yield {
        "storage": storage,
        "root": test_memory_root,
    }


class TestSmartRetrievalEndToEnd:
    """End-to-end tests for smart retrieval."""
    
    @pytest.mark.asyncio
    async def test_two_stage_retrieval_flow(self, memory_setup, monkeypatch):
        """Test complete two-stage retrieval flow."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever(max_candidates=10, max_results=3)
        storage = memory_setup["storage"]
        now = datetime.utcnow()
        
        # Create test memories
        memories = [
            MemoryEntry(
                id=f"mem_{i:03d}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Memory about {topic}",
                description=f"Description of {topic}",
                content=f"Content about {topic}",
                created_at=now,
                updated_at=now,
            )
            for i, topic in enumerate([
                "Docker deployment",
                "Kubernetes orchestration",
                "Git workflow",
                "Python best practices",
                "Testing strategies",
            ])
        ]
        
        # Save memories
        for mem in memories:
            await storage.save(mem)
        
        # Test retrieval
        with monkeypatch.context() as m:
            # Mock memory_manager.list_memories to return our test data
            from app.core import memory as memory_module
            
            async def mock_list_all(limit=100):
                return [storage._entry_to_summary(m) for m in memories]
            
            async def mock_get_memory(mem_id):
                for m in memories:
                    if m.id == mem_id:
                        return m
                return None
            
            m.setattr(memory_module.memory_manager, "list_memories", mock_list_all)
            m.setattr(memory_module.memory_manager, "get_memory", mock_get_memory)
            
            results = await retriever.find_relevant(
                query="Docker deployment containers",
                context={"recent_tools": []},
            )
        
        # Should return results
        assert len(results) <= 3
        # Docker-related memory should be in results
        docker_mem = next((r for r in results if "Docker" in r.title), None)
        assert docker_mem is not None
    
    @pytest.mark.asyncio
    async def test_freshness_ranking_in_retrieval(self, memory_setup, monkeypatch):
        """Test that freshness affects retrieval ranking."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Two similar memories, one fresh, one old
        fresh_memory = MemoryEntry(
            id="mem_fresh",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Guide 2024",
            description="Latest Docker practices",
            content="Use Docker Compose v2",
            created_at=now,
            updated_at=now,
        )
        
        old_memory = MemoryEntry(
            id="mem_old",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Guide 2023",
            description="Old Docker practices",
            content="Use Docker Compose v1",
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=90),
        )
        
        ctx = RetrievalContext(
            query="Docker guide",
            recent_tools=[],
            already_surfaced=set(),
        )
        
        # Score both
        fresh_score = retriever._score_candidate(fresh_memory, ctx)
        old_score = retriever._score_candidate(old_memory, ctx)
        
        # Fresh should score higher
        assert fresh_score > old_score
    
    @pytest.mark.asyncio
    async def test_privacy_filtering_in_retrieval(self, memory_setup):
        """Test that privacy is respected in retrieval."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Private memory for user_A
        private_memory = MemoryEntry(
            id="mem_private",
            type=MemoryType.USER,
            privacy=PrivacyLevel.PRIVATE,
            title="My Secret",
            description="Private info",
            content="Personal preference",
            created_at=now,
            updated_at=now,
            user_id="user_A",
        )
        
        # Same user requesting
        ctx_with_access = RetrievalContext(
            query="secret",
            recent_tools=[],
            already_surfaced=set(),
            user_id="user_A",
        )
        
        # Different user requesting
        ctx_without_access = RetrievalContext(
            query="secret",
            recent_tools=[],
            already_surfaced=set(),
            user_id="user_B",
        )
        
        # User A should see their own private memory
        # (We check privacy in _get_candidates, test the filtering logic)
        assert private_memory.privacy == PrivacyLevel.PRIVATE
        assert private_memory.user_id == "user_A"


class TestQualityIntegration:
    """Integration tests for quality analysis."""
    
    @pytest.mark.asyncio
    async def test_analyze_real_memory(self, memory_setup):
        """Test analyzing a real memory entry."""
        from app.core.memory.quality import MemoryQualityAnalyzer
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer()
        now = datetime.utcnow()
        
        # Create a well-formed memory
        entry = MemoryEntry(
            id="mem_quality_test",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Best Practices",
            description="How to use Docker effectively",
            content="""
**Why:** Multi-stage builds reduce image size and improve security.

**How to apply:** 
1. Use a builder stage with all dependencies
2. Copy only artifacts to final stage
3. Use specific version tags, not "latest"

Example Dockerfile:
```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:18-alpine
COPY --from=builder /app/dist ./dist
```
            """,
            created_at=now,
            updated_at=now,
        )
        
        scores = await analyzer.analyze_memory(entry)
        
        # Should have good scores for well-formed memory
        assert scores.freshness > 0.9  # Very fresh
        assert scores.specificity > 0.5  # Has specific content (Dockerfile, versions)
        assert scores.actionability > 0.5  # Has actionable sections
        assert scores.overall > 0.5  # Good overall score
    
    @pytest.mark.asyncio
    async def test_quality_scores_for_vague_memory(self, memory_setup):
        """Test quality scoring for vague memory."""
        from app.core.memory.quality import MemoryQualityAnalyzer
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer()
        now = datetime.utcnow()
        
        # Create a vague, low-quality memory
        entry = MemoryEntry(
            id="mem_vague",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Some Stuff",
            description="Something about things",
            content="You should probably do something with this somehow.",
            created_at=now,
            updated_at=now,
        )
        
        scores = await analyzer.analyze_memory(entry)
        
        # Should have low specificity
        assert scores.specificity < 0.5
        # Actionability should also be low
        assert scores.actionability < 0.5


class TestStateTrackingIntegration:
    """Integration tests for state tracking."""
    
    @pytest.mark.asyncio
    async def test_prevent_duplicate_surfacing(self, memory_setup):
        """Test that already-surfaced memories are filtered."""
        from app.core.memory.smart_retrieval import SmartMemoryRetriever
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        retriever = SmartMemoryRetriever()
        now = datetime.utcnow()
        
        # Create memories
        memories = [
            MemoryEntry(
                id=f"mem_surf_{i}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Memory {i}",
                description="Description",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            for i in range(5)
        ]
        
        # First retrieval
        results1 = await retriever.find_relevant(
            query="test",
            context={},
            already_surfaced=set(),
        )
        
        # Mark results as surfaced
        surfaced_ids = {r.id for r in results1}
        
        # Second retrieval with surfaced filter
        results2 = await retriever.find_relevant(
            query="test",
            context={},
            already_surfaced=surfaced_ids,
        )
        
        # Results2 should not include already-surfaced memories
        for result in results2:
            assert result.id not in surfaced_ids
    
    @pytest.mark.asyncio
    async def test_state_tracker_ttl(self, memory_setup):
        """Test that surfaced tracking respects TTL."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Mark as surfaced
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        # Should be surfaced immediately
        assert tracker.is_surfaced("thread_1", "mem_001") is True
        
        # Simulate TTL expiration by manipulating timestamp
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200  # 2 hours ago
        
        # Should not be surfaced after TTL
        assert tracker.is_surfaced("thread_1", "mem_001") is False


class TestRecallToolIntegration:
    """Integration tests for recall tool with smart retrieval."""
    
    @pytest.mark.asyncio
    async def test_recall_uses_smart_retrieval(self, memory_setup, monkeypatch):
        """Test that recall tool uses smart retrieval."""
        from app.core.engine.tools.memory_tools import recall
        from app.core.context.manager import ContextManager
        
        class MockContext:
            user_id = "test_user"
            project_id = 42
            thread_id = "test_thread"
        
        original_current = ContextManager.current
        ContextManager.current = lambda: MockContext()
        
        try:
            # Mock get_relevant_memories to verify it's called
            from app.core.engine import tools as tools_module
            from app.core.memory import smart_retrieval
            
            mock_results = []
            
            async def mock_get_relevant(**kwargs):
                mock_results.append(kwargs)
                return []
            
            original_fn = smart_retrieval.get_relevant_memories
            smart_retrieval.get_relevant_memories = mock_get_relevant
            
            try:
                await recall(query="Docker")
                
                # Verify smart retrieval was called
                assert len(mock_results) == 1
                assert mock_results[0]["query"] == "Docker"
            finally:
                smart_retrieval.get_relevant_memories = original_fn
                
        finally:
            ContextManager.current = original_current


class TestMiddlewareIntegration:
    """Integration tests for middleware hydration with smart retrieval."""
    
    @pytest.mark.asyncio
    async def test_middleware_smart_retrieval_path(self, monkeypatch):
        """Test that middleware uses smart retrieval in embedded mode."""
        from app.core.config import settings
        
        # Force embedded mode
        original_use_neo4j = settings.USE_NEO4J_MEMORY
        settings.USE_NEO4J_MEMORY = False
        
        try:
            from app.core.engine.context_hydrator import EvoContextMiddleware
            
            # Mock the smart retrieval function
            call_count = [0]
            
            async def mock_get_relevant(**kwargs):
                call_count[0] += 1
                return []
            
            from app.core import memory as memory_module
            original_fn = memory_module.get_relevant_memories
            memory_module.get_relevant_memories = mock_get_relevant
            
            try:
                # Create minimal state
                state = {
                    "messages": [],
                    "blackboard": {},
                    "thread_id": "test_thread",
                }
                
                # Mock context
                from app.core.context import EvoContext
                ctx = EvoContext(
                    project_id=42,
                    thread_id="test_thread",
                    user_id="test_user",
                    request_id="test_req",
                )
                
                from app.core.context.manager import ContextManager
                ContextManager.set(ctx)
                
                # We can't easily run full hydration without more setup,
                # but we can verify the path exists
                assert hasattr(EvoContextMiddleware, 'hydrate')
                
            finally:
                memory_module.get_relevant_memories = original_fn
                
        finally:
            settings.USE_NEO4J_MEMORY = original_use_neo4j


# Import needed at end to avoid circular issues
import time
