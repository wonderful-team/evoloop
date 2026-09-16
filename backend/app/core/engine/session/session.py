"""AgentSession — session-level resident run (one thread, one AgentState, multi-turn).

单 Agent ReAct 会话（重构目标架构，替代图引擎的 Supervisor/Worker/Finish 会话）。

- 会话在 ThreadGate 上挂起（无 LLM/CPU 消耗），由消息注入 / HITL 恢复 / 取消唤醒。
- 每条 user_message 是一次 delivery，包装在 activity_monitor.run_scope 内。
- 主循环 = run_agent_loop（单 Agent ReAct，engine/react/loop.py）。
- 运行中新消息语义（§3.5）：
  - 空闲 → queue（新一轮 delivery）
  - 运行中且相关 → steer（append 进当前消息流）
  - 停止/取消 → interrupt（协作式取消）
- HITL 挂起与恢复（§3.6）：工具抛 AgentHumanInterruptException → 挂起等恢复 →
  恢复后重建 state（DB 为准）续跑。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.agent.models import BackgroundAgentInputs
from app.core.engine.context_hydrator import AgentContextHydrator
from app.core.engine.error_emitter import error_emitter
from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.runner_base import (
    build_agent_state,
    build_ctx,
    build_execution_config,
)
from app.core.engine.session.gate import GateEvent, ThreadGate
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.monitoring.activity import activity_monitor
from app.utils.id import unique_id

logger = logging.getLogger(__name__)


class AgentSession:
    """Resident session for a single thread."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self.gate = ThreadGate()
        self.state: Any | None = None
        self.lifecycle: str = "running"  # running -> closed
        self.pending_resume: BackgroundAgentInputs | None = None
        self.idle_since: float | None = None
        # 阻塞式调用方（值守等）等待"本轮 delivery 完成"的事件
        self._delivery_done: asyncio.Event | None = None

    def inject_user_message(
        self, inputs: dict[str, Any] | BackgroundAgentInputs
    ) -> None:
        self.gate.put(GateEvent(kind="user_message", payload={"inputs": inputs}))

    def inject_resume(
        self,
        hitl_resume_response: str,
        *,
        is_cancel: bool = False,
        kind: str = "hitl_response",
        project_id: int | None = None,
        grant_mode: str | None = None,
    ) -> None:
        """注入恢复事件。``kind``：``hitl_response`` | ``a2a_result``。

        A2A 结果已被 ``update_content_by_tool_call_id`` 写入 DB，会话只重建 state
        reload 被改写消息并续跑，不走 HITL 原语。``grant_mode``：审批 once/always。
        """
        self.gate.put(
            GateEvent(
                kind="user_message",
                payload={
                    "hitl_resume_response": hitl_resume_response,
                    "is_hitl_cancel": is_cancel,
                    "resume_kind": kind,
                    "project_id": project_id,
                    "grant_mode": grant_mode,
                },
            )
        )

    async def cancel(self, reason: str = "user_cancelled") -> None:
        """取消当前 run，会话保留可复用（标准停止语义）。"""
        await activity_monitor.stop_run(self.thread_id)
        self.gate.put(GateEvent(kind="session_cancel", payload={"reason": reason}))

    async def stop(self, reason: str = "user_cancelled") -> None:
        """完整停止会话：取消当前 run 并关闭（不再复用）。"""
        await self.cancel(reason)
        self.gate.put(GateEvent(kind="session_close", payload={"reason": reason}))

    async def wait_delivery_complete(self, timeout: float | None = None) -> bool:
        """等待本轮 delivery 完成（阻塞式调用方专用）。"""
        if self._delivery_done is None:
            self._delivery_done = asyncio.Event()
        try:
            await asyncio.wait_for(self._delivery_done.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._delivery_done.clear()


async def run_agent_session(session: AgentSession) -> None:
    """Main loop: one task for the session lifetime, multi-turn reusable."""
    ctx = await ContextManager.load(session.thread_id)
    if ctx is None:
        ctx = EvoContext(
            thread_id=session.thread_id,
            request_id=unique_id("req", session.thread_id),
        )
    ContextManager.set(ctx)

    try:
        while session.lifecycle == "running":
            try:
                ev = await asyncio.wait_for(
                    session.gate.wait_next(),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                # 周期检查 DB 停止标志（跨进程协作式停止）
                await activity_monitor.check_cancellation(session.thread_id)
                if getattr(session, "idle_since", None) is None:
                    session.idle_since = time.time()
                elif time.time() - session.idle_since > settings.SESSION_IDLE_TIMEOUT:
                    logger.info(f"[Session] {session.thread_id} idle timeout, closing")
                    break
                continue
            # 有事件到达 → 重置空闲计时
            session.idle_since = time.time()
            if ev.kind == "session_close":
                break
            if ev.kind == "session_cancel":
                await activity_monitor.stop_run(session.thread_id)
                logger.info(f"[Session] {session.thread_id} session cancelled")
                break
            if ev.kind == "user_message":
                await _run_delivery(session, inputs=_resolve_inputs(ev))
                _notify_delivery_done(session)
                continue
    except asyncio.CancelledError:
        logger.info(f"[Session] {session.thread_id} main loop cancelled")
        raise
    except AgentCancelledException:
        logger.info(f"[Session] {session.thread_id} main loop cancelled by stop")
    except Exception as e:
        logger.error(f"[Session] {session.thread_id} main loop crashed: {e}", exc_info=True)
        # 错误呈现单出口：分类→事件→SSE，契约见 tests/.../test_error_emitter.py
        await error_emitter.emit(
            session.thread_id, e, project_id=session.state.project_id if session.state else None
        )
    finally:
        session.lifecycle = "closed"
        _notify_delivery_done(session)
        logger.info(f"[Session] {session.thread_id} session closed")


def _notify_delivery_done(session: AgentSession) -> None:
    if session._delivery_done is not None:
        session._delivery_done.set()


def _resolve_inputs(ev: GateEvent) -> BackgroundAgentInputs | None:
    payload = ev.payload or {}
    if payload.get("hitl_resume_response") is not None:
        return BackgroundAgentInputs(
            hitl_resume_response=payload["hitl_resume_response"],
            is_hitl_cancel=bool(payload.get("is_hitl_cancel")),
            model=_current_model(),
            metadata={
                "_resume_kind": payload.get("resume_kind", "hitl_response"),
                "_grant_mode": payload.get("grant_mode"),
            },
        )
    raw = payload.get("inputs")
    if raw is None:
        return None
    return (
        raw if isinstance(raw, BackgroundAgentInputs) else BackgroundAgentInputs(**raw)
    )


async def _run_delivery(
    session: AgentSession,
    inputs: BackgroundAgentInputs | None,
) -> None:
    """One delivery (run_scope)."""
    project_id = inputs.project_id if inputs else DEFAULT_PROJECT_ID
    main_goal = (
        inputs.goal
        if inputs and inputs.goal
        else (session.state.session_goal if session.state else "session turn")
    )

    async with activity_monitor.run_scope(
        session.thread_id, main_goal, task_type="session", project_id=project_id
    ) as scope_run_id:
        try:
            if inputs is not None:
                await _refresh_session_ctx(session, inputs)
                session.state = await build_agent_state(session.thread_id, inputs)
            state = session.state
            if state is None:
                return
            config = await _build_session_config(session, inputs, scope_run_id)

            # 上下文水合（望远镜加载：intent 门控的 skills/macros/记忆）
            ctx = ContextManager.current()
            lc_config = {
                "configurable": config["configurable"],
                "metadata": config["metadata"],
            }
            await AgentContextHydrator.hydrate(
                ctx=ctx,
                state=state,
                config=lc_config,
                last_human_msg=inputs.session_goal if inputs else "",
                is_retry=bool(inputs and inputs.is_retry),
                iteration_count=inputs.iteration_count if inputs else 0,
            )

            await _run_turn(session, state, config, inputs)
            await ContextManager.save(session.thread_id)
        except AgentCancelledException:
            logger.info(f"[Session] {session.thread_id} delivery cancelled")
            raise
        except AgentHumanInterruptException:
            logger.info(f"[Session] {session.thread_id} HITL/A2A hang within scope")
            await _hang_for_resume(session)
            # 消费用户 HITL 答案：resume_and_persist 把 APPROVED 重执行/REJECTED
            # 文案写回 DB tool 消息（此前断链：pending_resume 无人读取，Agent
            # 永远收不到拒绝反馈，反复重试同一被拒操作）。
            resume_inputs = session.pending_resume
            session.pending_resume = None
            if resume_inputs:
                await _handle_resume(session, state, resume_inputs)


async def _run_turn(
    session: AgentSession,
    state: Any,
    config: dict[str, Any],
    inputs: BackgroundAgentInputs | None,
) -> None:
    """单 Agent ReAct 主循环（同步阻塞一轮 delivery，HITL 中断挂起-恢复）。

    §3.5 steer：主循环运行中，新 user 消息经 ``_steer_provider`` 直接 append 进
    当前消息流（替代排队）；空闲时仍走下一轮 delivery（queue）。
    """
    from app.core.engine.react.loop import run_agent_loop

    async def _steer_provider() -> list[Any]:
        msgs: list[Any] = []
        # 竞态保护：resume 事件可能早于 AgentHumanInterruptException 传播到挂起点
        # 到达（自动化客户端毫秒级响应）。此类事件不是 steer 消息，重新入队，
        # 由 _hang_for_resume 消费；在此排干会静默丢失用户的批准/拒绝答案。
        deferred_resumes: list[GateEvent] = []
        for ev in session.gate.drain():
            if ev.kind in ("session_cancel", "session_close"):
                raise AgentCancelledException("session cancelled while steering")
            if ev.kind == "user_message":
                payload = ev.payload or {}
                if payload.get("hitl_resume_response") is not None:
                    deferred_resumes.append(ev)
                    continue
                raw = payload.get("inputs")
                goal = None
                if isinstance(raw, dict):
                    goal = raw.get("session_goal") or raw.get("goal")
                elif raw is not None:
                    goal = getattr(raw, "session_goal", None) or getattr(
                        raw, "goal", None
                    )
                if goal:
                    msgs.append(HumanMessage(content=str(goal)))
        for ev in deferred_resumes:
            session.gate.put(ev)
        return msgs

    while True:
        try:
            await run_agent_loop(
                state,
                config,
                session.thread_id,
                log_prefix="SessionReact",
                steer_provider=_steer_provider,
            )
            break
        except AgentHumanInterruptException:
            await _hang_for_resume(session)
            # 消费用户 HITL 答案（写回 DB tool 消息），与外层 delivery 循环同语义
            resume_inputs = session.pending_resume
            session.pending_resume = None
            if resume_inputs:
                await _handle_resume(session, state, resume_inputs)
            # 恢复后重建 state（HITL 答案已写回 DB tool 消息）
            session.state = await build_agent_state(
                session.thread_id,
                inputs or BackgroundAgentInputs(model=_current_model()),
            )
            state = session.state
            continue
        except AgentCancelledException:
            raise


async def _hang_for_resume(session: AgentSession) -> None:
    """Parked inside the scope waiting for HITL/A2A resume or new input."""
    while True:
        try:
            ev = await asyncio.wait_for(session.gate.wait_next(), timeout=2.0)
        except asyncio.TimeoutError:
            await activity_monitor.check_cancellation(session.thread_id)
            continue
        if ev.kind == "session_cancel":
            raise AgentCancelledException("session cancelled while awaiting human")
        if ev.kind == "session_close":
            return
        if ev.kind == "user_message":
            payload = ev.payload or {}
            if payload.get("hitl_resume_response") is not None:
                session.pending_resume = BackgroundAgentInputs(
                    hitl_resume_response=payload["hitl_resume_response"],
                    is_hitl_cancel=bool(payload.get("is_hitl_cancel")),
                    model=_current_model(),
                    project_id=payload.get("project_id"),
                    metadata={
                        "_resume_kind": payload.get("resume_kind", "hitl_response"),
                        "_grant_mode": payload.get("grant_mode"),
                    },
                )
                return
            # awaiting_human 期间新 chat 消息按 HITL 答案处理（§4.5）
            raw = payload.get("inputs")
            if raw is not None:
                new_inputs = (
                    raw
                    if isinstance(raw, BackgroundAgentInputs)
                    else BackgroundAgentInputs(**raw)
                )
                session.pending_resume = BackgroundAgentInputs(
                    hitl_resume_response=new_inputs.goal or "",
                    model=new_inputs.model or _current_model(),
                    project_id=payload.get("project_id") or new_inputs.project_id,
                    metadata={"_resume_kind": "hitl_response"},
                )
            return


async def _handle_resume(
    session: AgentSession,
    state: Any,
    inputs: BackgroundAgentInputs,
) -> None:
    """HITL/A2A resume: close the pending request and write the tool result back."""
    ctx = ContextManager.current()
    thread_id = session.thread_id
    project_id = inputs.project_id or DEFAULT_PROJECT_ID

    config = {
        "configurable": {"thread_id": thread_id, "model": inputs.model},
        "metadata": {"project_id": project_id},
    }
    consumed = await HITLOrchestrator.resume_and_persist(
        thread_id=thread_id,
        project_id=project_id,
        member_id=ctx.member_id or 0,
        config=config,
        user_input=inputs.hitl_resume_response,
        state=state,
        grant_mode=(inputs.metadata or {}).get("_grant_mode"),
    )
    if not consumed:
        logger.info(f"[Session] resume without pending tool on {thread_id}, continuing")


async def _refresh_session_ctx(
    session: AgentSession, inputs: BackgroundAgentInputs
) -> None:
    """Per-turn injection refresh: request_id/command_id/active_model/token."""
    ctx = await build_ctx(session.thread_id, inputs)
    if inputs.metadata and inputs.metadata.get("token"):
        ctx.token = inputs.metadata["token"]
        ContextManager.set(ctx)


async def _build_session_config(
    session: AgentSession,
    inputs: BackgroundAgentInputs | None,
    run_id: str,
) -> dict[str, Any]:
    """Build session execution config + callbacks（复用共享 runner_base）。"""
    ctx = ContextManager.current()
    if inputs is None:
        inputs = BackgroundAgentInputs(model=_current_model())
    return build_execution_config(
        session.thread_id,
        ctx.project_id or DEFAULT_PROJECT_ID,
        inputs,
        run_id,
        ctx,
    )


async def _close_session(session: AgentSession) -> None:
    """关闭会话：标记 closed 并唤醒阻塞在 wait_delivery_complete 上的调用方。"""
    session.lifecycle = "closed"
    _notify_delivery_done(session)
    logger.info(f"[Session] {session.thread_id} session closed")


def _current_model() -> str | None:
    ctx = ContextManager.current()
    return getattr(ctx, "active_model", None)
