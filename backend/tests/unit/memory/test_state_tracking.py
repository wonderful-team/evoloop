"""
Unit tests for Memory State Tracking (Phase 3).

Tests memory surface tracking, TTL expiration, and cleanup.

Run with: pytest tests/unit/memory/test_state_tracking.py -v
"""

import pytest
import time
from datetime import datetime


class TestMemoryStateTrackerInit:
    """Tests for MemoryStateTracker initialization."""
    
    def test_default_initialization(self):
        """Test that tracker initializes with defaults."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        assert tracker._surfaced == {}
        assert tracker.DEFAULT_SURFACE_TTL == 3600  # 1 hour
        assert tracker._cleanup_interval == 300  # 5 minutes


class TestMarkSurfaced:
    """Tests for marking memories as surfaced."""
    
    def test_mark_single_memory(self):
        """Test marking a single memory as surfaced."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        assert "thread_1" in tracker._surfaced
        assert "mem_001" in tracker._surfaced["thread_1"]
    
    def test_mark_multiple_memories(self):
        """Test marking multiple memories at once."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        tracker.mark_surfaced("thread_1", ["mem_001", "mem_002", "mem_003"])
        
        assert len(tracker._surfaced["thread_1"]) == 3
        assert "mem_001" in tracker._surfaced["thread_1"]
        assert "mem_002" in tracker._surfaced["thread_1"]
        assert "mem_003" in tracker._surfaced["thread_1"]
    
    def test_mark_across_threads(self):
        """Test marking memories across different threads."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        tracker.mark_surfaced("thread_1", ["mem_001"])
        tracker.mark_surfaced("thread_2", ["mem_002"])
        
        assert "mem_001" in tracker._surfaced["thread_1"]
        assert "mem_002" in tracker._surfaced["thread_2"]
        assert "mem_001" not in tracker._surfaced["thread_2"]
    
    def test_mark_updates_timestamp(self):
        """Test that marking updates the timestamp."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        tracker.mark_surfaced("thread_1", ["mem_001"])
        first_time = tracker._surfaced["thread_1"]["mem_001"]
        
        time.sleep(0.01)  # Small delay
        
        tracker.mark_surfaced("thread_1", ["mem_001"])
        second_time = tracker._surfaced["thread_1"]["mem_001"]
        
        assert second_time > first_time


class TestGetSurfacedIds:
    """Tests for getting surfaced memory IDs."""
    
    def test_get_empty(self):
        """Test getting IDs when nothing is surfaced."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        ids = tracker.get_surfaced_ids("thread_1")
        
        assert ids == set()
    
    def test_get_surfaced(self):
        """Test getting surfaced IDs."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001", "mem_002"])
        
        ids = tracker.get_surfaced_ids("thread_1")
        
        assert ids == {"mem_001", "mem_002"}
    
    def test_ttl_expiration(self):
        """Test that old entries are filtered out by TTL."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Manually set old timestamp
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200  # 2 hours ago
        tracker._surfaced["thread_1"]["mem_002"] = time.time()  # Now
        
        # Default TTL is 1 hour, so mem_001 should be expired
        ids = tracker.get_surfaced_ids("thread_1")
        
        assert "mem_001" not in ids
        assert "mem_002" in ids
    
    def test_custom_ttl(self):
        """Test using custom TTL."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Set 10-second old timestamp
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 20
        
        # With 30-second TTL, should still be valid
        ids = tracker.get_surfaced_ids("thread_1", max_age=30)
        assert "mem_001" in ids
        
        # With 10-second TTL, should be expired
        ids = tracker.get_surfaced_ids("thread_1", max_age=10)
        assert "mem_001" not in ids


class TestIsSurfaced:
    """Tests for checking if a specific memory is surfaced."""
    
    def test_is_surfaced_true(self):
        """Test checking surfaced memory."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        assert tracker.is_surfaced("thread_1", "mem_001") is True
    
    def test_is_surfaced_false(self):
        """Test checking unsurfaced memory."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        assert tracker.is_surfaced("thread_1", "mem_999") is False
    
    def test_is_surfaced_expired(self):
        """Test that expired memories are not surfaced."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Set old timestamp
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200
        
        assert tracker.is_surfaced("thread_1", "mem_001") is False


class TestFilterFresh:
    """Tests for filtering out surfaced memories."""
    
    def test_filter_all_fresh(self):
        """Test filtering when all are fresh."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001"), MockEntry("mem_002")]
        
        fresh = tracker.filter_fresh("thread_1", entries)
        
        assert len(fresh) == 2
    
    def test_filter_some_surfaced(self):
        """Test filtering when some are surfaced."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001"), MockEntry("mem_002")]
        
        fresh = tracker.filter_fresh("thread_1", entries)
        
        assert len(fresh) == 1
        assert fresh[0].id == "mem_002"
    
    def test_filter_all_surfaced(self):
        """Test filtering when all are surfaced."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001", "mem_002"])
        
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001"), MockEntry("mem_002")]
        
        fresh = tracker.filter_fresh("thread_1", entries)
        
        assert len(fresh) == 0
    
    def test_filter_ignores_expired(self):
        """Test that expired surfaced entries are treated as fresh."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Mark as surfaced but with old timestamp
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200
        
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001")]
        
        fresh = tracker.filter_fresh("thread_1", entries)
        
        # Should be fresh because TTL expired
        assert len(fresh) == 1


class TestClearThread:
    """Tests for clearing thread tracking."""
    
    def test_clear_existing_thread(self):
        """Test clearing an existing thread."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker.mark_surfaced("thread_1", ["mem_001"])
        
        tracker.clear_thread("thread_1")
        
        assert "thread_1" not in tracker._surfaced
    
    def test_clear_nonexistent_thread(self):
        """Test clearing a thread that doesn't exist."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Should not raise
        tracker.clear_thread("nonexistent")


class TestCleanup:
    """Tests for periodic cleanup."""
    
    def test_cleanup_removes_expired(self):
        """Test that cleanup removes expired entries."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Add some entries
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200  # Expired
        tracker._surfaced["thread_1"]["mem_002"] = time.time()  # Fresh
        tracker._surfaced["thread_2"]["mem_003"] = time.time() - 7200  # Expired
        
        # Force cleanup
        tracker._maybe_cleanup()
        
        # Expired entries should be removed
        assert "mem_001" not in tracker._surfaced["thread_1"]
        assert "mem_002" in tracker._surfaced["thread_1"]
        assert "mem_003" not in tracker._surfaced.get("thread_2", {})
    
    def test_cleanup_removes_empty_threads(self):
        """Test that cleanup removes empty threads."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        
        # Add only expired entries to thread
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200
        
        # Force cleanup
        tracker._maybe_cleanup()
        
        # Empty thread should be removed
        assert "thread_1" not in tracker._surfaced
    
    def test_cleanup_respects_interval(self):
        """Test that cleanup respects the interval."""
        from app.core.memory.state_tracking import MemoryStateTracker
        
        tracker = MemoryStateTracker()
        tracker._last_cleanup = time.time()  # Just cleaned
        
        # Add expired entry
        tracker._surfaced["thread_1"]["mem_001"] = time.time() - 7200
        
        # Try cleanup (should skip due to interval)
        tracker._maybe_cleanup()
        
        # Should still be there (cleanup skipped)
        assert "mem_001" in tracker._surfaced["thread_1"]


class TestPredictiveMemoryCache:
    """Tests for predictive memory cache."""
    
    def test_cache_set_and_get(self):
        """Test setting and getting cache entries."""
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        cache = PredictiveMemoryCache()
        
        results = ["mem_001", "mem_002"]
        cache.set("thread_1", "query", results)
        
        cached = cache.get("thread_1", "query")
        
        assert cached == results
    
    def test_cache_miss(self):
        """Test cache miss."""
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        cache = PredictiveMemoryCache()
        
        cached = cache.get("thread_1", "nonexistent_query")
        
        assert cached is None
    
    def test_cache_expiration(self):
        """Test that cache entries expire."""
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        cache = PredictiveMemoryCache()
        cache._cache_ttl = 0.01  # 10ms for testing
        
        cache.set("thread_1", "query", ["mem_001"])
        
        # Should hit immediately
        assert cache.get("thread_1", "query") is not None
        
        # Wait for expiration
        time.sleep(0.02)
        
        # Should miss after expiration
        assert cache.get("thread_1", "query") is None
    
    def test_cache_clear_thread(self):
        """Test clearing cache for a thread."""
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        cache = PredictiveMemoryCache()
        
        cache.set("thread_1", "query1", ["mem_001"])
        cache.set("thread_2", "query2", ["mem_002"])
        
        cache.clear_thread("thread_1")
        
        assert cache.get("thread_1", "query1") is None
        assert cache.get("thread_2", "query2") is not None
    
    def test_cache_different_queries_same_thread(self):
        """Test that different queries are cached separately."""
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        cache = PredictiveMemoryCache()
        
        cache.set("thread_1", "query1", ["mem_001"])
        cache.set("thread_1", "query2", ["mem_002"])
        
        assert cache.get("thread_1", "query1") == ["mem_001"]
        assert cache.get("thread_1", "query2") == ["mem_002"]


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_mark_memories_surfaced(self):
        """Test mark_memories_surfaced convenience function."""
        from app.core.memory.state_tracking import (
            mark_memories_surfaced,
            memory_tracker,
        )
        
        mark_memories_surfaced("thread_1", ["mem_001", "mem_002"])
        
        assert "mem_001" in memory_tracker._surfaced["thread_1"]
        assert "mem_002" in memory_tracker._surfaced["thread_1"]
    
    def test_get_surfaced_memory_ids(self):
        """Test get_surfaced_memory_ids convenience function."""
        from app.core.memory.state_tracking import (
            get_surfaced_memory_ids,
            memory_tracker,
        )
        
        memory_tracker.mark_surfaced("thread_1", ["mem_001"])
        
        ids = get_surfaced_memory_ids("thread_1")
        
        assert "mem_001" in ids
    
    def test_filter_unsurfaced_memories(self):
        """Test filter_unsurfaced_memories convenience function."""
        from app.core.memory.state_tracking import (
            filter_unsurfaced_memories,
            memory_tracker,
        )
        
        memory_tracker.mark_surfaced("thread_1", ["mem_001"])
        
        class MockEntry:
            def __init__(self, id):
                self.id = id
        
        entries = [MockEntry("mem_001"), MockEntry("mem_002")]
        fresh = filter_unsurfaced_memories("thread_1", entries)
        
        assert len(fresh) == 1
        assert fresh[0].id == "mem_002"


class TestGlobalInstances:
    """Tests for global singleton instances."""
    
    def test_memory_tracker_singleton(self):
        """Test that global memory_tracker exists."""
        from app.core.memory.state_tracking import memory_tracker
        from app.core.memory.state_tracking import MemoryStateTracker
        
        assert isinstance(memory_tracker, MemoryStateTracker)
    
    def test_predictive_cache_singleton(self):
        """Test that global predictive_cache exists."""
        from app.core.memory.state_tracking import predictive_cache
        from app.core.memory.state_tracking import PredictiveMemoryCache
        
        assert isinstance(predictive_cache, PredictiveMemoryCache)
