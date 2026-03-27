"""
Abstract Cache Backend Interface for EvoLoop.

Provides a unified interface for cache operations, hiding the underlying
implementation (Redis in production, FileCache in embedded mode).
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Protocol


class PubSubBackend(ABC):
    """Abstract Pub/Sub interface for real-time event streaming."""

    @abstractmethod
    async def subscribe(self, *channels: str) -> None:
        """Subscribe to one or more channels."""
        ...

    @abstractmethod
    async def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from channels."""
        ...

    @abstractmethod
    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = None) -> dict | None:
        """Get message from subscribed channels (non-blocking with timeout)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close pub/sub connection."""
        ...


class CacheLock(ABC):
    """Abstract distributed lock interface."""

    @abstractmethod
    async def acquire(self, blocking: bool = True, blocking_timeout: float = None) -> bool:
        """Acquire the lock."""
        ...

    @abstractmethod
    async def release(self) -> None:
        """Release the lock."""
        ...

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
        return False


class Cache(ABC):
    """
    Abstract cache backend interface.
    
    Provides Redis-like operations that work with both Redis/FileCache (production)
    and FileCache (embedded mode) implementations.
    """

    # ========== Key-Value Operations ==========

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value by key."""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        """
        Set key to value with optional expiration (in seconds).
        
        Args:
            key: The key to set
            value: Value to store (will be JSON serialized if needed)
            ex: Expiration time in seconds (None = no expiration)
        """
        ...

    @abstractmethod
    async def setex(self, key: str, ex: int, value: Any) -> bool:
        """Set key with expiration (Redis-compatible signature)."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> int:
        """Delete key(s). Returns number of keys deleted."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        ...

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on existing key."""
        ...

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment key by amount (atomic)."""
        ...

    # ========== Hash Operations ==========

    @abstractmethod
    async def hget(self, name: str, key: str) -> Any | None:
        """Get field from hash."""
        ...

    @abstractmethod
    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        """
        Set field(s) in hash.
        
        Supports both single field and bulk operations:
            await hset("myhash", "field1", "value1")
            await hset("myhash", mapping={"field1": "v1", "field2": "v2"})
        """
        ...

    @abstractmethod
    async def hgetall(self, name: str) -> dict:
        """Get all fields from hash as dict."""
        ...

    @abstractmethod
    async def hdel(self, name: str, *keys: str) -> int:
        """Delete field(s) from hash. Returns number of fields deleted."""
        ...

    @abstractmethod
    async def hlen(self, name: str) -> int:
        """Get number of fields in hash."""
        ...

    # ========== Set Operations ==========

    @abstractmethod
    async def sadd(self, name: str, *values: Any) -> int:
        """Add member(s) to set. Returns number of new members added."""
        ...

    @abstractmethod
    async def scard(self, name: str) -> int:
        """Get number of members in set."""
        ...

    @abstractmethod
    async def srem(self, name: str, *values: Any) -> int:
        """Remove member(s) from set. Returns number of members removed."""
        ...

    @abstractmethod
    async def smembers(self, name: str) -> set:
        """Get all members of set."""
        ...

    @abstractmethod
    async def sismember(self, name: str, value: Any) -> bool:
        """Check if value is member of set."""
        ...

    # ========== List Operations ==========

    @abstractmethod
    async def lpush(self, name: str, *values: Any) -> int:
        """Push values to left of list. Returns new list length."""
        ...

    @abstractmethod
    async def ltrim(self, name: str, start: int, end: int) -> bool:
        """Trim list to specified range."""
        ...

    # ========== Pub/Sub ==========

    @abstractmethod
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel. Returns number of subscribers."""
        ...

    @abstractmethod
    def pubsub(self) -> PubSubBackend:
        """Get pub/sub client."""
        ...

    # ========== Locks ==========

    @abstractmethod
    def lock(self, name: str, timeout: float = None, blocking: bool = True, blocking_timeout: float = None) -> CacheLock:
        """Create a distributed lock."""
        ...

    # ========== Pipeline ==========

    @abstractmethod
    def pipeline(self) -> "CachePipeline":
        """Create a pipeline for batch operations."""
        ...

    # ========== Lifecycle ==========

    @abstractmethod
    async def close(self) -> None:
        """Close cache connection."""
        ...


class CachePipeline(ABC):
    """Abstract pipeline for batch operations."""

    @abstractmethod
    def get(self, key: str) -> "CachePipeline":
        """Queue get operation."""
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ex: int | None = None) -> "CachePipeline":
        """Queue set operation."""
        ...

    @abstractmethod
    def delete(self, *keys: str) -> "CachePipeline":
        """Queue delete operation."""
        ...

    @abstractmethod
    def hget(self, name: str, key: str) -> "CachePipeline":
        """Queue hget operation."""
        ...

    @abstractmethod
    def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> "CachePipeline":
        """Queue hset operation."""
        ...

    @abstractmethod
    def hgetall(self, name: str) -> "CachePipeline":
        """Queue hgetall operation."""
        ...

    @abstractmethod
    def hdel(self, name: str, *keys: str) -> "CachePipeline":
        """Queue hdel operation."""
        ...

    @abstractmethod
    def hlen(self, name: str) -> "CachePipeline":
        """Queue hlen operation."""
        ...

    @abstractmethod
    def sadd(self, name: str, *values: Any) -> "CachePipeline":
        """Queue sadd operation."""
        ...

    @abstractmethod
    def scard(self, name: str) -> "CachePipeline":
        """Queue scard operation."""
        ...

    @abstractmethod
    def srem(self, name: str, *values: Any) -> "CachePipeline":
        """Queue srem operation."""
        ...

    @abstractmethod
    async def execute(self) -> list[Any]:
        """Execute all queued operations and return results."""
        ...
