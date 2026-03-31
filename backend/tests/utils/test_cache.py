"""
Tests for app.utils.cache module.
"""

import time
import pytest

from app.utils.cache import (
    TTLCache,
    LRUCache,
    ttl_cache,
    lru_cache,
)


class TestTTLCache:
    """Test cases for TTLCache class."""

    def test_basic_set_get(self):
        """Test basic set and get operations."""
        cache = TTLCache()
        cache.set("key", "value", ttl=60)
        assert cache.get("key") == "value"
    
    def test_expired_entry(self):
        """Test expired entries are removed."""
        cache = TTLCache()
        cache.set("key", "value", ttl=0.01)
        time.sleep(0.02)
        assert cache.get("key") is None
    
    def test_missing_key(self):
        """Test getting missing key returns None."""
        cache = TTLCache()
        assert cache.get("nonexistent") is None
    
    def test_delete(self):
        """Test deleting a key."""
        cache = TTLCache()
        cache.set("key", "value", ttl=60)
        cache.delete("key")
        assert cache.get("key") is None
    
    def test_clear(self):
        """Test clearing all entries."""
        cache = TTLCache()
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_contains(self):
        """Test __contains__ method."""
        cache = TTLCache()
        cache.set("key", "value", ttl=60)
        assert "key" in cache
        assert "nonexistent" not in cache


class TestLRUCache:
    """Test cases for LRUCache class."""

    def test_basic_set_get(self):
        """Test basic set and get operations."""
        cache = LRUCache()
        cache.set("key", "value")
        assert cache.get("key") == "value"
    
    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = LRUCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # Access a, making b LRU
        cache.set("c", 3)  # Should evict b
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3
    
    def test_missing_key(self):
        """Test getting missing key returns None."""
        cache = LRUCache()
        assert cache.get("nonexistent") is None
    
    def test_custom_default(self):
        """Test custom default value."""
        cache = LRUCache()
        assert cache.get("key", default="default") == "default"


class TestTTLCacheDecorator:
    """Test cases for ttl_cache decorator."""

    def test_basic_caching(self):
        """Test basic caching behavior."""
        call_count = 0
        
        @ttl_cache(ttl_seconds=60)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = expensive_function(5)
        result2 = expensive_function(5)
        
        assert result1 == result2 == 10
        assert call_count == 1  # Should only be called once
    
    def test_different_args(self):
        """Test different arguments create different cache entries."""
        call_count = 0
        
        @ttl_cache(ttl_seconds=60)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x
        
        func(1)
        func(2)
        func(1)  # Should use cache
        
        assert call_count == 2
    
    def test_expiration(self):
        """Test cache expiration."""
        call_count = 0
        
        @ttl_cache(ttl_seconds=0.01)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x
        
        func(1)
        time.sleep(0.02)
        func(1)  # Should call again after expiration
        
        assert call_count == 2


class TestLRUCacheDecorator:
    """Test cases for lru_cache decorator."""

    def test_basic_caching(self):
        """Test basic caching behavior."""
        call_count = 0
        
        @lru_cache(maxsize=128)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = expensive_function(5)
        result2 = expensive_function(5)
        
        assert result1 == result2 == 10
        assert call_count == 1
    
    def test_maxsize_limit(self):
        """Test maxsize limit."""
        call_count = 0
        
        @lru_cache(maxsize=2)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x
        
        func(1)
        func(2)
        func(3)  # Should evict 1
        func(1)  # Should call again
        
        assert call_count == 4
