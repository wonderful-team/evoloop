"""
AgentRunRegistry — tracks running agent tasks (voice / text / L0 宏) per thread.

Allows new requests to check whether an agent run is currently active for a
thread, and cancel it (Esc×2 统一停止）。react 单 Agent 模式下，主循环本体由
AgentSession 承载；registry 只负责跟踪会话外独立注册的后台执行（如 L0 路由宏）
并提供取消兜底。图架构的 worker rollout / A2A wait 协调已删除。

（客户端可见的 ``has_running_worker`` / ``running_worker_desc`` 元数据键为
wire 契约，沿用旧名；本模块内部已统一为 run 语义。）
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.models.subagent import SubagentStatus

logger = logging.getLogger(__name__)


@dataclass
class RunRecord:
    task: asyncio.Task[Any] | None = None
    status: SubagentStatus = SubagentStatus.RUNNING
    description: str = ""
    started_at: float = 0.0
    result: str | None = None
    project_id: int | None = None


class AgentRunRegistry:
    """Global registry of running/completed agent runs per thread_id."""

    def __init__(self):
        self._records: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()

    async def register_run(
        self, thread_id: str, task: asyncio.Task[Any], description: str = ""
    ) -> None:
        async with self._lock:
            from app.core.context.thread_store import thread_context_store

            self._records[thread_id] = RunRecord(
                task=task,
                status=SubagentStatus.RUNNING,
                description=description,
                started_at=time.time(),
                project_id=thread_context_store.get_active_project(thread_id),
            )

    async def cancel_run(self, thread_id: str) -> bool:
        async with self._lock:
            record = self._records.pop(thread_id, None)
            # 级联取消 split 子任务（旧 worker 裂变的 subagent，run parent = <thread_id>-split-*）
            split_prefix = f"{thread_id}-split"
            split_records = [
                (tid, rec)
                for tid, rec in self._records.items()
                if tid.startswith(split_prefix)
            ]
            for tid, rec in split_records:
                self._records.pop(tid, None)
                if rec.task is not None and not rec.task.done():
                    rec.task.cancel()
        if record is not None and record.task is not None and not record.task.done():
            record.task.cancel()
            return True
        return bool(split_records)

    async def cancel_all(self, project_id: int | None = None) -> int:
        """取消所有注册的运行中任务（L0 宏等独立执行），返回取消数。

        ``project_id`` 给定则只取消该项目的任务（Esc×2 按项目停止时，
        宏任务与 session 同步过滤）；None = 取消全部。

        Esc×2 统一停止时，除了 session_manager 的活跃会话，还需覆盖
        agent_run_registry 里独立注册的任务（如 L0 路由宏）。
        """
        async with self._lock:
            tids = list(self._records.keys())
            cancelled = 0
            for tid in tids:
                record = self._records.get(tid)
                if (
                    project_id is not None
                    and record is not None
                    and record.project_id != project_id
                ):
                    continue
                record = self._records.pop(tid, None)
                if (
                    record is not None
                    and record.task is not None
                    and not record.task.done()
                ):
                    record.task.cancel()
                    cancelled += 1
        return cancelled

    async def get_run(self, thread_id: str) -> RunRecord | None:
        async with self._lock:
            record = self._records.get(thread_id)
            if record is None:
                return None
            # Clean up completed tasks
            if (
                record.status == SubagentStatus.RUNNING
                and record.task is not None
                and record.task.done()
            ):
                record.status = SubagentStatus.COMPLETED
            return record

    async def has_running_run(self, thread_id: str) -> bool:
        record = await self.get_run(thread_id)
        return record is not None and record.status == SubagentStatus.RUNNING


# Module singleton
agent_run_registry = AgentRunRegistry()
