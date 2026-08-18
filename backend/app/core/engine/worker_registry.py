"""
WorkerRegistry — tracks running Worker tasks for both voice and text channels.

Allows new requests to check if a Worker is currently running for a thread,
and query its status without canceling it. Used by Supervisor to decide
whether the user is asking about progress (query) or issuing a new command.

2026-08 (parent-run-liveness): the ``_previous_tasks`` replacement model is
removed — worker replacement is now handled by the session main loop
(AgentSession + structured NEW_COMMAND detection), so there is no "previous
task" concept anymore. Registry keeps register/get/cancel lifecycle only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkerRecord:
    task: asyncio.Task[Any] | None = None
    status: str = "running"  # running | completed | failed | cancelled
    description: str = ""
    started_at: float = 0.0
    result: str | None = None
    project_id: int | None = None


class WorkerRegistry:
    """Global registry of running/completed Workers per thread_id."""

    def __init__(self):
        self._records: dict[str, WorkerRecord] = {}
        self._lock = asyncio.Lock()

    async def register_worker(
        self, thread_id: str, task: asyncio.Task[Any], description: str = ""
    ) -> None:
        async with self._lock:
            from app.core.context.thread_store import thread_context_store

            self._records[thread_id] = WorkerRecord(
                task=task,
                status="running",
                description=description,
                started_at=time.time(),
                project_id=thread_context_store.get_active_project(thread_id),
            )

    async def complete_worker(self, thread_id: str, result: str | None = None) -> None:
        async with self._lock:
            record = self._records.get(thread_id)
            if record is not None:
                record.status = "completed"
                record.result = result

    async def fail_worker(self, thread_id: str, error: str | None = None) -> None:
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

    async def cancel_all(self, project_id: int | None = None) -> int:
        """取消所有注册的运行中任务（L0 宏等独立执行），返回取消数。

        ``project_id`` 给定则只取消该项目的任务（Esc×2 按项目停止时，
        宏任务与 session 同步过滤）；None = 取消全部。

        Esc×2 统一停止时，除了 session_manager 的活跃会话，还需覆盖
        worker_registry 里独立注册的任务（如 L0 路由宏）。
        """
        async with self._lock:
            tids = list(self._records.keys())
            cancelled = 0
            for tid in tids:
                record = self._records.get(tid)
                if project_id is not None and record is not None and record.project_id != project_id:
                    continue
                record = self._records.pop(tid, None)
                if record is not None and record.task is not None and not record.task.done():
                    record.task.cancel()
                    cancelled += 1
        return cancelled

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
