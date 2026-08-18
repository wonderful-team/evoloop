"""ThreadSessionManager — module singleton mapping thread_id → AgentSession."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.session.session import AgentSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Registry of live AgentSessions (one per thread)."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._lock = asyncio.Lock()

    def get(self, thread_id: str) -> AgentSession | None:
        return self._sessions.get(thread_id)

    async def get_or_create(self, thread_id: str) -> AgentSession:
        """Return the live session for a thread; create + start one if absent/closed."""
        existing = self._sessions.get(thread_id)
        if existing is not None and existing.lifecycle == "running":
            return existing

        from app.core.session.session import AgentSession, run_agent_session

        async with self._lock:
            existing = self._sessions.get(thread_id)
            if existing is not None and existing.lifecycle == "running":
                return existing

            session = AgentSession(thread_id)
            self._sessions[thread_id] = session
            asyncio.create_task(run_agent_session(session))
            logger.info(f"[SessionManager] Created session for thread {thread_id}")
            return session

    async def stop_agent(self, thread_id: str, reason: str = "user_cancelled") -> bool:
        """统一停止 Agent（voice/web/mobile 共用，标准停止语义）。

        - 有活会话 → ``session.stop``（取消当前 run + 关闭会话）。
        - 无活会话 → ``stop_run``（协作式标志，覆盖所有 Agent 检查点）
          + ``cancel_worker``（硬中断已注册的后台任务，如 L0 宏任务）。

        返回 True = 存在可停止的会话或任务。
        """
        session = self._sessions.get(thread_id)
        if session is not None and session.lifecycle == "running":
            await session.stop(reason)
            self._sessions.pop(thread_id, None)
            return True

        from app.core.engine.worker_registry import worker_registry
        from app.core.monitoring.activity import activity_monitor

        stopped = False
        if await worker_registry.cancel_worker(thread_id):
            stopped = True
        await activity_monitor.stop_run(thread_id)
        return stopped

    async def stop_all(
        self,
        reason: str = "user_cancelled",
        *,
        project_id: int | None = None,
        member_id: int | None = None,
    ) -> int:
        """统一停止活跃会话（Esc 两次停止等场景），可按 project/member 过滤。

        - ``project_id``：仅停该项目的会话；None = 不限项目。
        - ``member_id``：仅停该用户的会话；None = 不限用户。
        返回停止的会话数。逐个走 ``stop_agent``（有会话 → session.stop；
        无会话 → stop_run + cancel_worker 双兜底），语义与单端停止一致。
        """
        from app.core.context.thread_store import thread_context_store

        stopped = 0
        for tid in list(self._sessions.keys()):
            # 按 project 过滤（thread → project 关联）
            if project_id is not None:
                tid_project = thread_context_store.get_active_project(tid)
                if tid_project != project_id:
                    continue
            # 按 member 过滤（从 ctx 取 member_id）
            if member_id is not None:
                session_member = await self._session_member_id(tid)
                if session_member != member_id:
                    continue
            if await self.stop_agent(tid, reason):
                stopped += 1
        return stopped

    async def _session_member_id(self, thread_id: str) -> int | None:
        """从会话 ctx 取 member_id（用于 stop_all 按用户过滤）。"""
        from app.core.context.manager import ContextManager

        ctx = await ContextManager.load(thread_id)
        return ctx.member_id if ctx else None

    async def submit(
        self,
        thread_id: str,
        inputs: Any,
        *,
        await_completion: bool = False,
        timeout: float | None = None,
        is_resume: bool = False,
        is_cancel: bool = False,
    ) -> Any:
        """统一消息提交入口（各通道共用，替代直接调 run_agent_background）。

        - 无活会话 → get_or_create 创建并启动；有 → 复用。
        - ``is_resume``：HITL/A2A 恢复用 inject_resume，否则 inject_user_message。
        - ``is_cancel``：配合 is_resume 标记取消恢复。
        - ``await_completion``：阻塞等待本轮 delivery 完成（值守 duty 等场景）。
        """
        session = await self.get_or_create(thread_id)
        if is_resume:
            if isinstance(inputs, str):
                session.inject_resume(inputs, is_cancel=is_cancel)
            else:
                resume = getattr(inputs, "hitl_resume_response", None)
                inner_cancel = bool(getattr(inputs, "is_hitl_cancel", False))
                session.inject_resume(resume or "", is_cancel=inner_cancel or is_cancel)
        else:
            session.inject_user_message(inputs)
        if await_completion:
            await session.wait_delivery_complete(timeout=timeout)
        return session


# Module singleton
session_manager = SessionManager()
