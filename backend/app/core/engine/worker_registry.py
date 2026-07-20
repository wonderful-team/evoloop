"""
WorkerRegistry — tracks running Worker tasks for both voice and text channels.

Allows new requests to check if a Worker is currently running for a thread,
and query its status without canceling it. Used by Supervisor to decide
whether the user is asking about progress (query) or issuing a new command.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkerRecord:
    task: asyncio.Task[Any] | None = None
    status: str = "running"  # running | completed | failed | cancelled
    description: str = ""
    started_at: float = 0.0
    result: str | None = None


class WorkerRegistry:
    """Global registry of running/completed Workers per thread_id."""

    def __init__(self):
        self._records: dict[str, WorkerRecord] = {}
        self._lock = asyncio.Lock()

    async def register_worker(
        self, thread_id: str, task: asyncio.Task[Any], description: str = ""
    ) -> None:
        async with self._lock:
            self._records[thread_id] = WorkerRecord(
                task=task,
                status="running",
                description=description,
                started_at=__import__("time").time(),
            )

    async def complete_worker(
        self, thread_id: str, result: str | None = None
    ) -> None:
        async with self._lock:
            record = self._records.get(thread_id)
            if record is not None:
                record.status = "completed"
                record.result = result

    async def fail_worker(
        self, thread_id: str, error: str | None = None
    ) -> None:
        async with self._lock:
            record = self._records.get(thread_id)
            if record is not None:
                record.status = "failed"
                record.result = error

    async def cancel_worker(self, thread_id: str) -> bool:
        async with self._lock:
            record = self._records.pop(thread_id, None)
        if record is not None and record.task is not None and not record.task.done():
            record.task.cancel()
            return True
        return False

    async def get_worker(self, thread_id: str) -> WorkerRecord | None:
        async with self._lock:
            record = self._records.get(thread_id)
            if record is None:
                return None
            # Clean up completed tasks
            if record.status == "running" and record.task is not None and record.task.done():
                record.status = "completed"
            return record

    async def has_running_worker(self, thread_id: str) -> bool:
        record = await self.get_worker(thread_id)
        return record is not None and record.status == "running"


# Module singleton
worker_registry = WorkerRegistry()
