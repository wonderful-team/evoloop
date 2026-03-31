"""
Tests for LayeredContextCache

Run with: pytest tests/test_context_cache.py -v
"""

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from types import ModuleType

# Create mock modules
for mod_name in ['app', 'app.core', 'app.core.memory', 'app.core.learning']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = ModuleType(mod_name)

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.engine.context_cache import (
    StaticContextLayer,
    DynamicContextLayer,
    LayeredContextCache,
)


class TestStaticContextLayer:
    """Test StaticContextLayer dataclass."""
    
    def test_creation(self):
        """Should create with default values."""
        layer = StaticContextLayer()
        
        assert layer.project_concepts is None
        assert layer.active_skills_index == []
        assert layer.environment_telemetry == {}
        assert layer.project_id == 0
        assert time.time() - layer.cached_at < 1
    
    def test_is_valid_within_ttl(self):
        """Should be valid within TTL."""
        layer = StaticContextLayer(cached_at=time.time() - 100)  # 100s ago
        
        assert layer.is_valid(max_age=300) is True  # 5min TTL
    
    def test_is_valid_expired(self):
        """Should be invalid after TTL."""
        layer = StaticContextLayer(cached_at=time.time() - 400)  # 400s ago
        
        assert layer.is_valid(max_age=300) is False


class TestDynamicContextLayer:
    """Test DynamicContextLayer dataclass."""
    
    def test_creation(self):
        """Should create with default values."""
        layer = DynamicContextLayer()
        
        assert layer.blackboard == {}
        assert layer.execution_ticket is None
        assert layer.messages == []
        assert layer.iteration_count == 0
    
    def test_with_data(self):
        """Should hold dynamic data correctly."""
        layer = DynamicContextLayer(
            blackboard={"ticket": {"topic": "test"}},
            iteration_count=3,
        )
        
        assert layer.blackboard["ticket"]["topic"] == "test"
        assert layer.iteration_count == 3


class TestLayeredContextCache:
    """Test LayeredContextCache class."""
    
    def setup_method(self):
        """Clear cache before each test."""
        LayeredContextCache._static_cache.clear()
        LayeredContextCache._stats = {
            'static_hits': 0,
            'static_misses': 0,
            'dynamic_loads': 0,
        }
    
    @pytest.mark.asyncio
    async def test_static_layer_cache_miss(self):
        """First call should load and cache."""
        mock_loader = AsyncMock(return_value={
            'project_concepts': 'Test concepts',
            'active_skills': ['skill1', 'skill2'],
            'telemetry': {'android': []},
        })
        
        layer = await LayeredContextCache.get_static_layer(
            session_id="sess123",
            project_id=1,
            loader_fn=mock_loader
        )
        
        assert layer.project_concepts == 'Test concepts'
        assert layer.active_skills_index == ['skill1', 'skill2']
        mock_loader.assert_called_once()
        
        # Should be cached
        assert "sess123:1" in LayeredContextCache._static_cache
    
    @pytest.mark.asyncio
    async def test_static_layer_cache_hit(self):
        """Second call should use cache."""
        mock_loader = AsyncMock(return_value={
            'project_concepts': 'Test concepts',
            'active_skills': ['skill1'],
        })
        
        # First call
        await LayeredContextCache.get_static_layer("sess123", 1, mock_loader)
        mock_loader.assert_called_once()
        
        # Second call - should hit cache
        mock_loader.reset_mock()
        layer = await LayeredContextCache.get_static_layer("sess123", 1, mock_loader)
        
        assert layer.project_concepts == 'Test concepts'
        mock_loader.assert_not_called()
        
        stats = LayeredContextCache.get_stats()
        assert stats['static_hits'] == 1
        assert stats['static_misses'] == 1
    
    @pytest.mark.asyncio
    async def test_static_layer_ttl_expiration(self):
        """Cache should expire after TTL."""
        mock_loader = AsyncMock(return_value={
            'project_concepts': 'Test',
            'active_skills': [],
        })
        
        # First call
        await LayeredContextCache.get_static_layer("sess123", 1, mock_loader)
        
        # Expire the cache
        for key in LayeredContextCache._static_cache:
            LayeredContextCache._static_cache[key].cached_at = time.time() - 400
        
        # Second call should reload
        mock_loader.reset_mock()
        await LayeredContextCache.get_static_layer("sess123", 1, mock_loader)
        
        mock_loader.assert_called_once()
    
    def test_dynamic_layer_always_fresh(self):
        """Dynamic layer should never be cached."""
        state = {
            "blackboard": {"ticket": {"topic": "test"}},
            "execution_ticket": {"id": 123},
            "messages": [{"type": "human", "content": "hello"}],
            "iteration_count": 5,
        }
        
        layer1 = LayeredContextCache.get_dynamic_layer(state)
        layer2 = LayeredContextCache.get_dynamic_layer(state)
        
        # Both should be independent copies
        assert layer1.blackboard == layer2.blackboard
        assert layer1 is not layer2  # Different objects
        
        stats = LayeredContextCache.get_stats()
        assert stats['dynamic_loads'] == 2  # Called twice
    
    def test_dynamic_layer_blackboard_isolation(self):
        """Modifying returned blackboard should not affect cache."""
        state = {
            "blackboard": {"key": "value"},
        }
        
        layer = LayeredContextCache.get_dynamic_layer(state)
        layer.blackboard["key"] = "modified"
        
        # Original state should be unchanged (we made a copy)
        assert state["blackboard"]["key"] == "value"
    
    def test_invalidation_by_session(self):
        """Should invalidate specific session."""
        # Add entries
        LayeredContextCache._static_cache["sess1:1"] = StaticContextLayer(project_id=1)
        LayeredContextCache._static_cache["sess1:2"] = StaticContextLayer(project_id=2)
        LayeredContextCache._static_cache["sess2:1"] = StaticContextLayer(project_id=1)
        
        # Invalidate sess1
        LayeredContextCache.invalidate_static("sess1")
        
        assert "sess1:1" not in LayeredContextCache._static_cache
        assert "sess1:2" not in LayeredContextCache._static_cache
        assert "sess2:1" in LayeredContextCache._static_cache  # Preserved
    
    def test_invalidation_by_project(self):
        """Should invalidate all entries for a project."""
        LayeredContextCache._static_cache["sess1:1"] = StaticContextLayer(project_id=1)
        LayeredContextCache._static_cache["sess2:1"] = StaticContextLayer(project_id=1)
        LayeredContextCache._static_cache["sess1:2"] = StaticContextLayer(project_id=2)
        
        # Invalidate project 1
        LayeredContextCache.invalidate_static(project_id=1)
        
        assert "sess1:1" not in LayeredContextCache._static_cache
        assert "sess2:1" not in LayeredContextCache._static_cache
        assert "sess1:2" in LayeredContextCache._static_cache  # Preserved
    
    def test_stats_calculation(self):
        """Stats should calculate correctly."""
        # Simulate some activity
        LayeredContextCache._stats['static_hits'] = 80
        LayeredContextCache._stats['static_misses'] = 20
        LayeredContextCache._stats['dynamic_loads'] = 100
        
        stats = LayeredContextCache.get_stats()
        
        assert stats['static_hits'] == 80
        assert stats['static_misses'] == 20
        assert stats['static_hit_rate'] == '80.0%'
        assert stats['dynamic_loads'] == 100
        assert stats['estimated_time_saved_ms'] == 16000  # 80 * 200ms
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Should clean up expired entries."""
        now = time.time()
        
        # Add fresh and stale entries
        LayeredContextCache._static_cache["fresh:1"] = StaticContextLayer(
            cached_at=now - 100
        )
        LayeredContextCache._static_cache["stale:1"] = StaticContextLayer(
            cached_at=now - 700  # 11+ minutes ago
        )
        
        await LayeredContextCache.cleanup_expired(max_age=600)
        
        assert "fresh:1" in LayeredContextCache._static_cache
        assert "stale:1" not in LayeredContextCache._static_cache


class TestLayeredCacheIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_full_hydration_flow(self):
        """Test the full hydration flow."""
        # Clear cache
        LayeredContextCache._static_cache.clear()
        
        # Mock data loader
        async def mock_loader():
            await asyncio.sleep(0.01)  # Simulate DB latency
            return {
                'project_concepts': 'Project context',
                'active_skills': ['skill1', 'skill2', 'skill3'],
                'telemetry': {'android': [], 'macos': True},
            }
        
        # Simulate multiple nodes in same request
        # Node 1: Supervisor
        t0 = time.time()
        static1 = await LayeredContextCache.get_static_layer("req1", 1, mock_loader)
        t1 = time.time()
        
        # Node 2: Worker
        static2 = await LayeredContextCache.get_static_layer("req1", 1, mock_loader)
        t2 = time.time()
        
        # Node 3: Finish
        static3 = await LayeredContextCache.get_static_layer("req1", 1, mock_loader)
        t3 = time.time()
        
        # First call should take longer (cache miss)
        duration1 = (t1 - t0) * 1000
        duration2 = (t2 - t1) * 1000
        duration3 = (t3 - t2) * 1000
        
        assert duration1 > 5  # At least 10ms for mock sleep
        assert duration2 < 1  # Cache hit, very fast
        assert duration3 < 1  # Cache hit, very fast
        
        # All should have same data
        assert static1.project_concepts == static2.project_concepts == static3.project_concepts
    
    def test_concurrent_dynamic_access(self):
        """Dynamic layer should be safe for concurrent access."""
        state = {
            "blackboard": {"counter": 0},
            "messages": [],
        }
        
        layers = []
        for _ in range(100):
            layer = LayeredContextCache.get_dynamic_layer(state)
            layers.append(layer)
        
        # All should be independent
        assert len(set(id(l.blackboard) for l in layers)) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
