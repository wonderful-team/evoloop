"""
Memory State Tracking - Prevent duplicate memory presentations

This module tracks which memories have already been shown to the user
to avoid repetitive "Did you know..." moments.

Tracking Strategies:
1. Session-scoped: Memories shown in current session (cleared on new session)
2. Request-scoped: Memories shown in current request (for multi-turn reasoning)
"""

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class MemoryStateTracker:
    """
    Track which memories have been surfaced to prevent repetition.
    
    This is session-scoped tracking. Memories are tracked until the session
    expires (after inactivity timeout) or the thread is closed.
    """

    # TTL in seconds - memories are "fresh" again after this period
    DEFAULT_SURFACE_TTL = 3600  # 1 hour

    def __init__(self):
        # thread_id -> {memory_id: timestamp}
        self._surfaced: dict[str, dict[str, float]] = defaultdict(dict)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def mark_surfaced(self, thread_id: str, memory_ids: list[str]) -> None:
        """
        Mark memories as having been shown to the user.
        
        Args:
            thread_id: The conversation thread ID
            memory_ids: List of memory IDs to mark
        """
        now = time.time()
        for mem_id in memory_ids:
            self._surfaced[thread_id][mem_id] = now

        if memory_ids:
            logger.debug(f"[MemoryTracker] Marked {len(memory_ids)} memories as surfaced for thread {thread_id}")

        # Periodic cleanup
        self._maybe_cleanup()

    def get_surfaced_ids(self, thread_id: str, max_age: float | None = None) -> set[str]:
        """
        Get IDs of memories already shown to the user.
        
        Args:
            thread_id: The conversation thread ID
            max_age: Maximum age in seconds (default: DEFAULT_SURFACE_TTL)
            
        Returns:
            Set of memory IDs that have been surfaced
        """
        max_age = max_age or self.DEFAULT_SURFACE_TTL
        now = time.time()

        surfaced = self._surfaced.get(thread_id, {})

        # Filter by age - expired entries are "fresh" again
        valid_ids = {
            mem_id for mem_id, timestamp in surfaced.items()
            if (now - timestamp) < max_age
        }

        return valid_ids

    def is_surfaced(self, thread_id: str, memory_id: str, max_age: float | None = None) -> bool:
        """Check if a specific memory has been surfaced."""
        return memory_id in self.get_surfaced_ids(thread_id, max_age)

    def filter_fresh(
        self,
        thread_id: str,
        entries: list,
        max_age: float | None = None,
    ) -> list:
        """
        Filter out already-surfaced memories from a list.
        
        Args:
            thread_id: The conversation thread ID
            entries: List of memory entry objects (must have .id attribute)
            max_age: Maximum age in seconds for considering "already shown"
            
        Returns:
            List of entries that haven't been surfaced (or are expired)
        """
        surfaced_ids = self.get_surfaced_ids(thread_id, max_age)
        return [e for e in entries if getattr(e, 'id', None) not in surfaced_ids]

    def clear_thread(self, thread_id: str) -> None:
        """Clear tracking for a specific thread."""
        self._surfaced.pop(thread_id, None)
        logger.debug(f"[MemoryTracker] Cleared tracking for thread {thread_id}")

    def _maybe_cleanup(self) -> None:
        """Periodic cleanup of expired entries."""
        now = time.time()
        if (now - self._last_cleanup) < self._cleanup_interval:
            return

        self._last_cleanup = now
        expired_threads = []

        for thread_id, memories in self._surfaced.items():
            # Remove expired entries
            expired_ids = [
                mem_id for mem_id, timestamp in memories.items()
                if (now - timestamp) >= self.DEFAULT_SURFACE_TTL
            ]
            for mem_id in expired_ids:
                del memories[mem_id]

            # Mark empty threads for removal
            if not memories:
                expired_threads.append(thread_id)

        for thread_id in expired_threads:
            del self._surfaced[thread_id]

        if expired_threads or expired_ids:
            logger.debug(f"[MemoryTracker] Cleanup: removed {len(expired_threads)} empty threads")


# Global instance
memory_tracker = MemoryStateTracker()


class PredictiveMemoryCache:
    """
    Cache for predictive memory loading (per-request scope).
    
    Unlike MemoryStateTracker which is session-scoped, this is for
    single-request caching to avoid duplicate searches.
    """

    def __init__(self):
        # thread_id -> {query_hash: (timestamp, results)}
        self._cache: dict[str, dict[str, tuple]] = {}
        self._cache_ttl = 60  # 60 seconds

    def get(self, thread_id: str, query: str) -> list | None:
        """Get cached results for a query."""
        import hashlib

        query_hash = hashlib.md5(query.encode()).hexdigest()[:16]
        thread_cache = self._cache.get(thread_id, {})

        if query_hash in thread_cache:
            timestamp, results = thread_cache[query_hash]
            if (time.time() - timestamp) < self._cache_ttl:
                return results
            else:
                # Expired
                del thread_cache[query_hash]

        return None

    def set(self, thread_id: str, query: str, results: list) -> None:
        """Cache results for a query."""
        import hashlib

        query_hash = hashlib.md5(query.encode()).hexdigest()[:16]

        if thread_id not in self._cache:
            self._cache[thread_id] = {}

        self._cache[thread_id][query_hash] = (time.time(), results)

    def clear_thread(self, thread_id: str) -> None:
        """Clear cache for a thread."""
        self._cache.pop(thread_id, None)


# Global cache instance
predictive_cache = PredictiveMemoryCache()


# Convenience functions
def mark_memories_surfaced(thread_id: str, memory_ids: list[str]) -> None:
    """Mark memories as surfaced."""
    memory_tracker.mark_surfaced(thread_id, memory_ids)


def get_surfaced_memory_ids(thread_id: str) -> set[str]:
    """Get IDs of surfaced memories."""
    return memory_tracker.get_surfaced_ids(thread_id)


def filter_unsurfaced_memories(thread_id: str, entries: list) -> list:
    """Filter out already-surfaced memories."""
    return memory_tracker.filter_fresh(thread_id, entries)
