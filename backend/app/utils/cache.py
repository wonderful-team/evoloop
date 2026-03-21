"""
Caching Utilities

Provides generic caching mechanisms with TTL (Time To Live) support,
LRU (Least Recently Used) cache, and cache decorators.
"""

import functools
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """
    Thread-safe in-memory cache with TTL (Time To Live) support.
    
    Automatically expires entries after the specified TTL.
    """
    
    def __init__(self, default_ttl: float = 300.0):
        """
        Initialize TTL cache.
        
        Args:
            default_ttl: Default TTL in seconds (default: 5 minutes)
        """
        self._cache: dict[K, tuple[V, float]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
    
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            default: Default value if key not found or expired
        
        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._cache:
                return default
            
            value, expiry = self._cache[key]
            if time.time() > expiry:
                # Expired
                del self._cache[key]
                return default
            
            return value
    
    def set(self, key: K, value: V, ttl: Optional[float] = None) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if not specified)
        """
        with self._lock:
            expiry = time.time() + (ttl if ttl is not None else self._default_ttl)
            self._cache[key] = (value, expiry)
    
    def delete(self, key: K) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key
        
        Returns:
            True if key existed and was deleted
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
    
    def invalidate(self, key: K) -> None:
        """Alias for delete()."""
        self.delete(key)
    
    def invalidate_all(self) -> None:
        """Alias for clear()."""
        self.clear()
    
    def keys(self) -> list[K]:
        """Get all non-expired keys."""
        with self._lock:
            now = time.time()
            return [k for k, (_, expiry) in self._cache.items() if expiry > now]
    
    def clean_expired(self) -> int:
        """
        Remove expired entries.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            expired = [k for k, (_, expiry) in self._cache.items() if expiry <= now]
            for k in expired:
                del self._cache[k]
            return len(expired)
    
    def __len__(self) -> int:
        """Return number of non-expired entries."""
        return len(self.keys())
    
    def __contains__(self, key: K) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None


class LRUCache(Generic[K, V]):
    """
    Thread-safe LRU (Least Recently Used) cache with size limit.
    """
    
    def __init__(self, maxsize: int = 128):
        """
        Initialize LRU cache.
        
        Args:
            maxsize: Maximum number of entries (default: 128)
        """
        self._maxsize = maxsize
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.RLock()
    
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get value and mark as recently used.
        
        Args:
            key: Cache key
            default: Default value if key not found
        
        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._cache:
                return default
            
            # Move to end (most recently used)
            value = self._cache.pop(key)
            self._cache[key] = value
            return value
    
    def set(self, key: K, value: V) -> None:
        """
        Set value, evicting oldest if at capacity.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            if key in self._cache:
                # Update existing
                self._cache.pop(key)
            elif len(self._cache) >= self._maxsize:
                # Evict oldest
                self._cache.popitem(last=False)
            
            self._cache[key] = value
    
    def delete(self, key: K) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key
        
        Returns:
            True if key existed and was deleted
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
    
    def keys(self) -> list[K]:
        """Get all keys (most recent first)."""
        with self._lock:
            return list(reversed(self._cache.keys()))
    
    def __len__(self) -> int:
        """Return number of entries."""
        return len(self._cache)
    
    def __contains__(self, key: K) -> bool:
        """Check if key exists."""
        return key in self._cache


def ttl_cache(ttl_seconds: float = 300.0):
    """
    Decorator to cache function results with TTL.
    
    Args:
        ttl_seconds: Time to live in seconds
    
    Example:
        @ttl_cache(ttl_seconds=60)
        def get_user(user_id: int) -> dict:
            return fetch_from_db(user_id)
    """
    cache = TTLCache(ttl_seconds)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Create key from arguments
            key = (args, tuple(sorted(kwargs.items())))
            
            # Try cache
            result = cache.get(key)
            if result is not None:
                return result
            
            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(key, result, ttl_seconds)
            return result
        
        # Attach cache methods
        wrapper.cache = cache  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore
        
        return wrapper
    
    return decorator


def lru_cache(maxsize: int = 128):
    """
    Decorator to cache function results with LRU eviction.
    
    Args:
        maxsize: Maximum cache size
    
    Example:
        @lru_cache(maxsize=256)
        def compute_expensive(x: int, y: int) -> int:
            return x * y
    """
    cache = LRUCache(maxsize)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            key = (args, tuple(sorted(kwargs.items())))
            
            result = cache.get(key)
            if result is not None:
                return result
            
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        
        wrapper.cache = cache  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore
        
        return wrapper
    
    return decorator


class CachedProperty:
    """
    Property decorator that caches the result.
    
    Similar to functools.cached_property but with optional TTL.
    """
    
    def __init__(self, func: Callable[..., T], ttl: Optional[float] = None):
        self.func = func
        self.ttl = ttl
        self.name = func.__name__
        self.cache: dict[int, tuple[T, float]] = {}
    
    def __get__(self, instance: Any, owner: type) -> T:
        if instance is None:
            return self  # type: ignore
        
        instance_id = id(instance)
        
        if instance_id in self.cache:
            value, expiry = self.cache[instance_id]
            if self.ttl is None or time.time() < expiry:
                return value
        
        value = self.func(instance)
        expiry = time.time() + self.ttl if self.ttl else float('inf')
        self.cache[instance_id] = (value, expiry)
        
        return value
    
    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name


def cached_property(ttl: Optional[float] = None):
    """
    Decorator for cached properties.
    
    Args:
        ttl: Optional TTL in seconds
    
    Example:
        class MyClass:
            @cached_property(ttl=60)
            def expensive_computation(self) -> dict:
                return compute_something()
    """
    def decorator(func: Callable[..., T]) -> CachedProperty:
        return CachedProperty(func, ttl)
    return decorator
