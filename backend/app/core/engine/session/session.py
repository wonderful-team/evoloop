"""AgentSession — session-level resident run (one thread, one AgentState, multi-turn).

A session parks on its ThreadGate when the Supervisor has no work (no LLM/CPU
consumed), and is woken by message injection / rollout completion / cancel.
The parent Supervisor can keep answering new questions while a worker rollout
runs in the background (parent-run-liveness-design.md).

Delivery model: each ``user_message`` or ``worker_completed`` is one "delivery"
wrapped in its own ``activity_monitor.run_scope`` (per-turn run_id). While a
rollout runs, the loop parks on the gate inside the scope (scope stays open).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.background_agent.worker_rollout import (
    _reload_worker_state,
    run_worker_rollout,
)
from app.core.engine.context_hydrator import AgentContextHydrator
from app.core.engine.loop import run_node_loop
from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.routers import RoutingTarget
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


@dataclass
class RolloutHandle:
    """Current background rollout (single Worker ReAct loop) for the session."""

    task: asyncio.Task[Any]
    rollout_id: str = field(default_factory=lambda: unique_id("ro", use_ms=True))
    description: str = ""

    @property
    def done(self) -> bool:
        return self.task.done()


class AgentSession:
    """Resident session for a single thread."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self.gate = ThreadGate()
        self.state: Any | None = None
        self.worker: RolloutHandle | None = None
        self.lifecycle: str = "running"  # running -> closed
        self.pending_resume: BackgroundAgentInputs | None = None
        self.idle_since: float | None = None
        # 阻塞式调用方（值守等）等待"本轮 delivery 完成"的事件
        self._delivery_done: asyncio.Event | None = None

    def inject_user_message(
        self, inputs: dict[str, Any] | BackgroundAgentInputs
    ) -> None:
        self.gate.put(GateEvent(kind="user_message", payload={"inputs": inputs}))

    def inject_worker_completed(self, rollout_id: str) -> None:
        self.gate.put(
            GateEvent(kind="worker_completed", payload={"rollout_id": rollout_id})
        )

    def inject_resume(
        self,
        hitl_resume_response: str,
        *,
        is_cancel: bool = False,
        kind: str = "hitl_response",
        project_id: int | None = None,
    ) -> None:
        """注入恢复事件。``kind``：``hitl_response``（§4.5）| ``a2a_result``（§4.6）。

        A2A 结果已被 ``update_content_by_tool_call_id`` 写入 DB，会话只重建 state
        reload 被改写消息并续跑，不走 HITL 原语。

        ``project_id``：HITL 请求上下文的项目 id，随事件透传，避免 resume 后
        落库的消息丢失 project_id（退回 DEFAULT_PROJECT_ID=0）。
        """
        self.gate.put(
            GateEvent(
                kind="user_message",
                payload={
                    "hitl_resume_response": hitl_resume_response,
                    "is_hitl_cancel": is_cancel,
                    "resume_kind": kind,
                    "project_id": project_id,
                },
            )
        )

    # ── 统一生命周期接口（AgentSession 对外标准语义）──────────────
    #
    # 会话是常驻多轮对象：start 由 get_or_create 隐式触发（幂等）；
    # stop / cancel 提供统一控制。
    # wait_delivery_complete 供"阻塞式"调用方（如值守 duty）等待本轮
    # delivery 真正跑完再取下一个联系人。

    async def cancel(self, reason: str = "user_cancelled") -> None:
        """取消当前 run，会话保留可复用（标准停止语义）。

        ⚠ 必须同时 ``activity_monitor.stop_run``（signal_stop）：主循环若在
        ``run_node_loop`` 内执行，gate 事件不会被消费，只有 loop 每步的
        ``check_cancellation`` 能立即中断当前 run（§4.3）。gate 事件用于主循环
        在挂起态（worker/HITL）时也能收到取消。
        """
        await activity_monitor.stop_run(self.thread_id)
        self.gate.put(GateEvent(kind="session_cancel", payload={"reason": reason}))

    async def stop(self, reason: str = "user_cancelled") -> None:
        """完整停止会话：取消当前 run 并关闭（不再复用）。

        标准对外停止入口（voice/web/mobile 停止当前任务后会话关闭，
        用户再说话经 get_or_create 重建，历史从 DB 恢复）。
        """
        await self.cancel(reason)
        self.gate.put(GateEvent(kind="session_close", payload={"reason": reason}))

    async def wait_delivery_complete(self, timeout: float | None = None) -> bool:
        """等待本轮 delivery 完成（阻塞式调用方专用）。

        返回 True = 本轮完成（含取消/失败）；False = 超时。
        会话主循环在每次 delivery 结束后 set ``self._delivery_done``。
        """
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
                # 挂起等待 gate 事件；每 2s 检查一次 DB 停止标志（跨进程协作式停止）。
                # worker 进程的值守会话在两次 delivery 之间挂起于此，API 进程
                # 写入的 stopping 标志不会被 gate 事件触发，需周期性感知。
                # check_cancellation 在 stopping 时抛 AgentCancelledException，
                # 由外层 except AgentCancelledException 捕获退出。
                ev = await asyncio.wait_for(
                    session.gate.wait_next(),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                await activity_monitor.check_cancellation(session.thread_id)
                # 每 2s 唤醒一次仅用于检查停止标志；真正的空闲收尾由
                # SESSION_IDLE_TIMEOUT 计时，见 idle_since。
                # 仅当无活跃 rollout 时累计空闲时间（rollout 执行中不算 idle）。
                if session.worker is not None and not session.worker.done:
                    session.idle_since = None
                    continue
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
                await _handle_session_cancel(session)
                break
            if ev.kind == "worker_completed":
                if not _is_current_rollout(session, ev):
                    continue  # 旧 rollout 的迟到事件（被 cancel），忽略
                # Worker 报告已在 rollout 中落库并推送，不再触发聚合 delivery
                # （避免 Supervisor 聚合轮二次回复用户）。_run_turn 内部通常已
                # 消费该事件；此处为兜底：仅通知 delivery 完成，会话等待新消息。
                _notify_delivery_done(session)
                continue
            if ev.kind == "subagent_completed":
                # subagent 完成事件（见 subagent_events._wake_session）：以聚合轮重进图。
                # 若仍在下发流程中则忽略，由 prepare_state 下一次调度统一消费。
                if (
                    getattr(session, "worker", None) is not None
                    and not session.worker.done
                ):
                    continue
                # 标记聚合轮：Supervisor 据此在"还有 subagent 在跑"时跳过 LLM 直接
                # 等待，避免陈旧上下文抢跑（重复委派 / 误 cancel）。
                await _run_delivery(session, inputs=None, aggregation_turn=True)
                _notify_delivery_done(session)
                continue
            if ev.kind == "subagent_hitl_request":
                # subagent HITL 透传事件：Supervisor 需跑 LLM 处理透传。
                if (
                    getattr(session, "worker", None) is not None
                    and not session.worker.done
                ):
                    continue
                await _run_delivery(session, inputs=None)
                _notify_delivery_done(session)
                continue
            if ev.kind == "user_message":
                await _run_delivery(session, inputs=_resolve_inputs(ev))
                _notify_delivery_done(session)
                continue
    except asyncio.CancelledError:
        logger.info(f"[Session] {session.thread_id} main loop cancelled")
        raise
    except AgentCancelledException:
        # 取消（stop/cancel）非崩溃：静默收尾，不当作 crash。
        logger.info(f"[Session] {session.thread_id} main loop cancelled by stop")
    except Exception as e:
        logger.error(
            f"[Session] {session.thread_id} main loop crashed: {e}", exc_info=True
        )
    finally:
        await _close_session(session)


def _notify_delivery_done(session: AgentSession) -> None:
    """Set the delivery-done event so blocking callers (duty) can proceed."""
    if session._delivery_done is not None:
        session._delivery_done.set()


def _resolve_inputs(ev: GateEvent) -> BackgroundAgentInputs | None:
    payload = ev.payload or {}
    if payload.get("hitl_resume_response") is not None:
        return BackgroundAgentInputs(
            hitl_resume_response=payload["hitl_resume_response"],
            is_hitl_cancel=bool(payload.get("is_hitl_cancel")),
            model=_current_model(),
            metadata={"_resume_kind": payload.get("resume_kind", "hitl_response")},
        )
    raw = payload.get("inputs")
    if raw is None:
        return None
    return (
        raw if isinstance(raw, BackgroundAgentInputs) else BackgroundAgentInputs(**raw)
    )


def _is_current_rollout(session: AgentSession, ev: GateEvent) -> bool:
    """校验 worker_completed 事件是否属于当前 rollout（防旧 rollout cancel 迟到事件混淆）。"""
    if session.worker is None:
        return False
    return ev.payload.get("rollout_id") == session.worker.rollout_id


async def _rollout_outcome(session: AgentSession) -> str:
    """读取当前 rollout 的 outcome（worker_completed 事件发出时 task 已 done）。

    HITL 中断时 run_worker_rollout 正常返回 ``"interrupted"``（非异常）。
    """
    if session.worker is None or session.worker.task is None:
        return ""
    try:
        if session.worker.task.done():
            return session.worker.task.result()
        return await asyncio.shield(session.worker.task)
    except Exception:
        return ""


def _should_run_finish_audit(state: Any | None) -> bool:
    """监察决策（Phase C.5）：仅当委托时 Supervisor 显式设置 needs_audit=true，
    Worker 交付才经监察者（Finish）验收；默认 false 直接呈现。"""
    return bool(state and state.ticket and state.ticket.needs_audit)


async def _reload_session_state(
    session: AgentSession, state: Any, config: dict
) -> Any | None:
    """重载 Worker 完成后的 state（DB 为准，含 A2A 回调结果写入的工具消息），
    并保留审计必需的 tool_history / worker_outcome。"""

    reloaded = await _reload_worker_state(state, config, session.thread_id)
    if reloaded is None:
        return None
    reloaded.tool_history = list(state.tool_history or [])
    reloaded.worker_outcome = state.worker_outcome
    return reloaded


async def _run_delivery(
    session: AgentSession,
    inputs: BackgroundAgentInputs | None,
    aggregation_turn: bool = False,
) -> None:
    """One delivery (run_scope). ``inputs is None`` ⇒ aggregation turn after a rollout.

    ``aggregation_turn=True``：subagent_completed 唤醒（无用户新消息），在 state 上
    打标记，Supervisor 据此在"还有 subagent 在跑"时跳过 LLM 等待聚合。
    """
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
            if aggregation_turn and session.state is not None:
                session.state.subagent_aggregation_turn = True
            if inputs is not None:
                await _refresh_session_ctx(session, inputs)
                session.state = await build_agent_state(session.thread_id, inputs)
            else:
                await _refresh_session_ctx(
                    session, BackgroundAgentInputs(model=_current_model())
                )

            state = session.state
            if state is None:
                return
            if inputs is None:
                # 聚合轮（worker 完成后）：强制从 Supervisor 重进图消费 worker_outcome
                state.next_node = "supervisor"
            config = await _build_session_config(session, inputs, scope_run_id)

            # 上下文水合（与单发 run_agent_background 一致）：填充 ctx.metadata 的
            # project_concepts / active_skills / memory raw 等，供 Supervisor/Worker
            # prompt 构建读取。缺失会导致会话场景 prompt 缺项目/技能/记忆上下文。

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
            # ⚠ 必须 re-raise：若在此吞掉，run_scope 会认为 yield 段正常结束而
            #    end_run(done)（§4.7 取消终态），stop/cancel 失效。由 run_scope 的
            #    except AgentCancelledException 处理 end_run(cancelled)。
            logger.info(f"[Session] {session.thread_id} delivery cancelled")
            raise
        except AgentHumanInterruptException:
            # 主循环在 scope 内捕获 —— scope 不退出（§4.7 推论 3），挂起等恢复。
            logger.info(f"[Session] {session.thread_id} HITL/A2A hang within scope")
            await _hang_for_resume(session)


async def _run_turn(
    session: AgentSession,
    state: Any,
    config: dict[str, Any],
    inputs: BackgroundAgentInputs | None,
) -> None:
    """Graph loop + rollout handoff + hang/resume. Scope stays open until delivery ends."""
    while True:
        if getattr(session, "pending_resume", None) is not None:
            inputs = session.pending_resume
            session.pending_resume = None
        try:
            if inputs is not None and inputs.hitl_resume_response:
                if (inputs.metadata or {}).get("_resume_kind") == "a2a_result":
                    # A2A 结果已被 update_content_by_tool_call_id 写入 DB：重建 state
                    # reload 被改写消息，续跑不混用 HITL 原语（§4.6）。
                    session.state = await build_agent_state(session.thread_id, inputs)
                    state = session.state
                else:
                    await _handle_resume(session, state, inputs)
                    # 恢复结果已 persist 到 DB（同 tool_call_id）；重建 state 让 LLM 可见，
                    # 否则内存 state 仍停在 waiting_human 的 tool_call（§4.5 恢复后执行）。
                    session.state = await build_agent_state(session.thread_id, inputs)
                    state = session.state
                inputs = None  # resume 已写回 DB/state，本轮以 state 重进图
            await run_node_loop(
                state,
                config,
                session.thread_id,
                log_prefix="Session",
                session_mode=True,
            )
        except AgentHumanInterruptException:
            await _hang_for_resume(session)
            continue
        except AgentCancelledException:
            raise

        # Worker handoff: Supervisor decided a new WORKER target.
        if getattr(state, "session_handoff", False):
            state.session_handoff = False
            await _start_rollout(session, state, config)
            while True:
                ev = await session.gate.wait_next()
                if ev.kind == "session_cancel":
                    raise AgentCancelledException(
                        "session cancelled while worker running"
                    )
                if ev.kind == "session_close":
                    return
                if ev.kind == "worker_completed":
                    if not _is_current_rollout(session, ev):
                        continue  # 旧 rollout 迟到事件，忽略
                    # rollout 若因 HITL（敏感文件批准等）中断：请求已注册，
                    # 挂起等待 _handle_resume 注入批准/拒绝。恢复后 break 出内层
                    # 循环，由外层 loop 顶部消费 pending_resume 继续执行——
                    # 否则 pending_resume 设了但没有新 delivery 会挂起。
                    rollout_outcome = await _rollout_outcome(session)
                    if rollout_outcome == "interrupted":
                        await _hang_for_resume(session)
                        break
                    # needs_audit=true：Worker 交付需经监察者（Finish）验收后再呈现。
                    # 重载 state（DB 为准，含 A2A 回调结果）+ 保留 tool_history/worker_outcome
                    # → 置 next_node=finish → 跳出内层循环，由外层 run_node_loop 跑验收
                    # （session_mode=True 保障 INCOMPLETE 回 Supervisor 时的 handoff 语义）。
                    if rollout_outcome == "done" and _should_run_finish_audit(state):
                        reloaded = await _reload_session_state(session, state, config)
                        if reloaded is not None:
                            session.state = reloaded
                            state = reloaded
                            state.next_node = RoutingTarget.FINISH
                            break
                    # 默认（needs_audit=false）：Worker 报告已在 rollout 中落库并推送给
                    # 用户 —— 这就是本轮交付的终点。不再回 Supervisor 聚合（避免
                    # Supervisor 把已完成任务误判为新任务重复派发 / 二次回复用户）。
                    return
                if ev.kind == "user_message":
                    state.next_node = "supervisor"
                    await _append_turn_input(state, ev)
                    break
            continue

        break  # 图跑到 END → 本轮交付完成


async def _hang_for_resume(session: AgentSession) -> None:
    """Parked inside the scope waiting for HITL/A2A resume or new input."""
    while True:
        try:
            ev = await asyncio.wait_for(session.gate.wait_next(), timeout=2.0)
        except asyncio.TimeoutError:
            # 周期检查 DB 停止标志（跨进程协作式停止，同主循环）
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
                        "_resume_kind": payload.get("resume_kind", "hitl_response")
                    },
                )
                return
            # awaiting_human 期间新 chat 消息按 HITL 答案处理（§4.5），消除并发 run 风险
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
        # worker_completed during hang → loop continues and Supervisor aggregates


async def _handle_resume(
    session: AgentSession,
    state: Any,
    inputs: BackgroundAgentInputs,
) -> None:
    """HITL/A2A resume: close the pending request and write the tool result back (runner-equivalent)."""

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
    )
    if not consumed:
        logger.info(f"[Session] resume without pending tool on {thread_id}, continuing")


async def _append_turn_input(state: Any | None, ev: GateEvent) -> None:
    if state is None:
        return
    payload = ev.payload or {}
    raw = payload.get("inputs")
    if raw is None:
        return
    inputs = (
        raw if isinstance(raw, BackgroundAgentInputs) else BackgroundAgentInputs(**raw)
    )

    state.messages.append(HumanMessage(content=inputs.goal or ""))


async def _handle_session_cancel(session: AgentSession) -> None:
    await _cancel_rollout(session)
    await activity_monitor.stop_run(session.thread_id)
    logger.info(f"[Session] {session.thread_id} session cancelled")


async def _close_session(session: AgentSession) -> None:
    await _cancel_rollout(session)
    session.lifecycle = "closed"
    # 唤醒阻塞在 wait_delivery_complete 上的调用方（如值守串行等待）：
    # 会话被停止/关闭/崩溃时也要让等待返回，否则值守扫描永久挂起，
    # next_run_at 不落盘 → 重启后任务又被重新派发。
    _notify_delivery_done(session)
    logger.info(f"[Session] {session.thread_id} session closed")


async def _cancel_rollout(session: AgentSession) -> None:
    if session.worker is not None and not session.worker.done:
        session.worker.task.cancel()
        try:
            await session.worker.task
        except (asyncio.CancelledError, Exception):
            logger.info(f"[Session] {session.thread_id} rollout cancelled")
    session.worker = None


# ---------------------------------------------------------------------------
# State / config / ctx builders
# ---------------------------------------------------------------------------


async def _refresh_session_ctx(
    session: AgentSession, inputs: BackgroundAgentInputs
) -> None:
    """Per-turn injection refresh: request_id/command_id/active_model/token (token rotation).

    复用共享 ``runner_base.build_ctx``（加载/刷新 EvoContext），并补充 token 旋转。
    """

    ctx = await build_ctx(session.thread_id, inputs)
    if inputs.metadata and inputs.metadata.get("token"):
        ctx.token = inputs.metadata["token"]
        ContextManager.set(ctx)


async def _build_session_config(
    session: AgentSession,
    inputs: BackgroundAgentInputs | None,
    run_id: str,
) -> dict[str, Any]:
    """Build session execution config + callbacks（复用共享 runner_base）。

    聚合轮（worker 完成后 inputs=None）用当前模型构造占位 inputs；
    会话轮直接用传入 inputs。
    """

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


async def _start_rollout(
    session: AgentSession, state: Any, config: dict[str, Any]
) -> None:
    """Cancel previous rollout (if any) and launch a new Worker ReAct rollout task."""
    if session.worker is not None and not session.worker.done:
        logger.info(
            f"[Session] {session.thread_id} cancelling previous rollout before handoff"
        )
        await _cancel_rollout(session)

    task = asyncio.create_task(run_worker_rollout(state, config, session.thread_id))
    handle = RolloutHandle(task=task, description=state.session_goal or "")
    session.worker = handle

    def _on_done(_t: asyncio.Task) -> None:
        # Wake the session loop; outcome was written back into shared state.
        session.inject_worker_completed(handle.rollout_id)

    task.add_done_callback(_on_done)


def _current_model() -> str | None:
    ctx = ContextManager.current()
    return getattr(ctx, "active_model", None)
