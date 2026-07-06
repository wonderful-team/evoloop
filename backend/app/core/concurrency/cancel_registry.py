"""
CancelRegistry — central registry for mid-execution run cancellation.

Maintains a map of thread_id -> (asyncio.Task, asyncio.Event, owner_id).
Cancellation sets the event (zero-latency local check) and calls
task.cancel() (asyncio preemption). This complements the existing
DB-based cooperative polling (check_cancellation) with instant local
interruption.

Inspired by CowAgent's CancelRegistry (/cancel second-level interrupt),
adapted for Evoloop's asyncio task model.

Usage:
    # On run start:
    cancel_registry.register("thread-123", asyncio.current_task(), owner_id=42)

    # On cancel request (from /chat/stop or godcmd #stop):
    await cancel_registry.cancel("thread-123", requester_id=42)

    # In the ReAct loop (replaces or supplements DB polling):
    if cancel_registry.is_cancelled("thread-123"):
        raise AgentCancelledException(...)

    # On run end:
    cancel_registry.unregister("thread-123")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CancellableRun:
    """Tracks a single cancellable run."""
    thread_id: str
    task: asyncio.Task | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    owner_id: int | None = None
    registered_at: datetime = field(default_factory=datetime.now)
    cancelled_at: datetime | None = None
    child_thread_ids: list[str] = field(default_factory=list)


class CancelRegistry:
    """
    Central registry for mid-execution cancellation.

    - register(): Called when a background run starts. Retains the asyncio.Task
      handle for .cancel() preemption.
    - cancel(): Sets the asyncio.Event (zero-latency signal) and calls
      task.cancel() (asyncio preemption). Propagates to child runs.
    - is_cancelled(): Checks the event — no DB poll, no TTL cache, instant.
    - unregister(): Cleanup on run completion (success or failure).
    """

    def __init__(self):
        self._runs: dict[str, CancellableRun] = {}
        self._guard = asyncio.Lock()

    async def register(
        self,
        thread_id: str,
        task: asyncio.Task | None = None,
        owner_id: int | None = None,
        parent_thread_id: str | None = None,
    ) -> CancellableRun:
        """Register a new cancellable run."""
        run = CancellableRun(
            thread_id=thread_id,
            task=task,
            owner_id=owner_id,
        )
        async with self._guard:
            self._runs[thread_id] = run
            if parent_thread_id and parent_thread_id in self._runs:
                self._runs[parent_thread_id].child_thread_ids.append(thread_id)

        logger.info("[CancelRegistry] Registered run %s (owner=%s)", thread_id, owner_id)
        return run

    async def cancel(self, thread_id: str, requester_id: int | None = None) -> bool:
        """
        Cancel a registered run.

        Args:
            thread_id: The run to cancel.
            requester_id: Who is requesting cancellation (for auth check).

        Returns:
            True if cancellation was signalled, False if run not found.
        """
        async with self._guard:
            run = self._runs.get(thread_id)

        if run is None:
            logger.warning("[CancelRegistry] Cancel requested for unknown run %s", thread_id)
            return False

        run.cancelled_at = datetime.now()
        run.event.set()

        if run.task and not run.task.done():
            run.task.cancel()
            logger.info("[CancelRegistry] Task.cancel() called for %s", thread_id)

        for child_id in run.child_thread_ids:
            await self.cancel(child_id, requester_id)

        logger.info("[CancelRegistry] Cancelled run %s (requester=%s, children=%d)",
                     thread_id, requester_id, len(run.child_thread_ids))
        return True

    def is_cancelled(self, thread_id: str) -> bool:
        """
        Zero-latency cancellation check.

        Checks the in-memory asyncio.Event — no DB poll, no TTL cache.
        Use this in hot loops (ReAct iterations, token streaming) to
        supplement the existing DB-based check_cancellation.
        """
        run = self._runs.get(thread_id)
        if run is None:
            return False
        return run.event.is_set()

    async def get_run(self, thread_id: str) -> CancellableRun | None:
        """Get the CancellableRun for a thread_id, if registered."""
        async with self._guard:
            return self._runs.get(thread_id)

    async def unregister(self, thread_id: str) -> None:
        """Remove a run from the registry (call on run completion)."""
        async with self._guard:
            self._runs.pop(thread_id, None)
        logger.debug("[CancelRegistry] Unregistered run %s", thread_id)

    def active_runs(self) -> list[str]:
        """Get list of thread_ids with active (registered) runs."""
        return list(self._runs.keys())

    def active_count(self) -> int:
        """Get count of active runs."""
        return len(self._runs)

    async def cancel_all(self) -> int:
        """Cancel all active runs (admin/godcmd use). Returns count cancelled."""
        thread_ids = list(self._runs.keys())
        count = 0
        for tid in thread_ids:
            if await self.cancel(tid):
                count += 1
        logger.info("[CancelRegistry] cancel_all: cancelled %d runs", count)
        return count


#: Global singleton
cancel_registry = CancelRegistry()
