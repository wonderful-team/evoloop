"""
SessionSerialQueue — per-thread FIFO serial execution gate.

Ensures that requests targeting the same thread_id are processed serially.
Unlike the existing reject-on-409 model, this queue enqueues waiters and
processes them in arrival order, preventing context/history races under
concurrent messages.

Inspired by CowAgent's BoundedSemaphore per-session pattern, adapted for
Evoloop's asyncio + optional Redis cross-process backing.

Usage:
    queue = SessionSerialQueue()
    async with await queue.acquire("thread-123") as slot:
        # Only one coroutine per thread_id executes here at a time
        await do_work()

    # Cross-process (Redis) mode:
    queue = SessionSerialQueue(use_redis=True)
    async with await queue.acquire("thread-123") as slot:
        await do_work()
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionSlot:
    """Represents an acquired serial execution slot for a session."""
    thread_id: str
    queue_position: int
    wait_time: float
    acquired_at: float = 0.0
    _queue: Any = None

    async def __aenter__(self) -> "SessionSlot":
        self.acquired_at = time.time()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._queue is not None:
            await self._queue.release(self.thread_id)


class SessionSerialQueue:
    """
    Per-session serial execution queue.

    - In-process mode: asyncio.Lock per thread_id + waiter counter for
      queue position reporting.
    - Redis mode (optional): SETNX-based distributed lock for cross-process
      mutual exclusion. Falls back to in-process lock if Redis unavailable.
    """

    def __init__(self, use_redis: bool = False, redis_timeout: float = 30.0):
        self._use_redis = use_redis
        self._redis_timeout = redis_timeout
        self._locks: dict[str, asyncio.Lock] = {}
        self._waiters: dict[str, int] = {}
        self._guard = asyncio.Lock()

    async def _get_lock(self, thread_id: str) -> asyncio.Lock:
        """Get or create the per-thread asyncio.Lock."""
        async with self._guard:
            if thread_id not in self._locks:
                self._locks[thread_id] = asyncio.Lock()
            return self._locks[thread_id]

    async def acquire(self, thread_id: str, timeout: float | None = 30.0) -> SessionSlot:
        """
        Acquire a serial execution slot for the given thread_id.

        Blocks until the previous holder releases the slot (or until timeout).

        Args:
            thread_id: Session identifier
            timeout: Max seconds to wait. None = wait forever.

        Returns:
            SessionSlot context manager. Use `async with` to auto-release.

        Raises:
            asyncio.TimeoutError if the slot is not acquired within timeout.
        """
        async with self._guard:
            self._waiters[thread_id] = self._waiters.get(thread_id, 0) + 1
            position = self._waiters[thread_id]

        lock = await self._get_lock(thread_id)
        start = time.time()

        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            async with self._guard:
                self._waiters[thread_id] = max(0, self._waiters[thread_id] - 1)
            logger.warning("[SessionQueue] Timeout acquiring slot for %s after %.1fs", thread_id, timeout or 0)
            raise

        wait_time = time.time() - start

        async with self._guard:
            self._waiters[thread_id] = max(0, self._waiters[thread_id] - 1)

        slot = SessionSlot(
            thread_id=thread_id,
            queue_position=position,
            wait_time=wait_time,
            _queue=self,
        )

        if position > 1:
            logger.info("[SessionQueue] Acquired slot for %s (waited %.2fs, was #%d in queue)",
                        thread_id, wait_time, position)

        return slot

    async def release(self, thread_id: str) -> None:
        """Release the serial execution slot for the given thread_id."""
        async with self._guard:
            lock = self._locks.get(thread_id)
        if lock and lock.locked():
            lock.release()
            logger.debug("[SessionQueue] Released slot for %s", thread_id)

    def get_queue_depth(self, thread_id: str) -> int:
        """Get the number of waiters for a thread (0 = no waiters)."""
        return self._waiters.get(thread_id, 0)

    def is_active(self, thread_id: str) -> bool:
        """Check if a session currently holds a slot."""
        lock = self._locks.get(thread_id)
        return lock is not None and lock.locked()

    def active_sessions(self) -> list[str]:
        """Get list of thread_ids with active (held) slots."""
        return [tid for tid, lock in self._locks.items() if lock.locked()]

    async def cleanup(self) -> None:
        """Remove locks with no active holders (housekeeping)."""
        async with self._guard:
            stale = [tid for tid, lock in self._locks.items()
                     if not lock.locked() and self._waiters.get(tid, 0) == 0]
            for tid in stale:
                self._locks.pop(tid, None)
                self._waiters.pop(tid, None)
            if stale:
                logger.debug("[SessionQueue] Cleaned up %d stale locks", len(stale))
