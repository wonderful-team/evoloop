"""Worker rollout — standalone Worker ReAct loop (session-mode background execution).

A rollout shares the parent ``AgentState`` instance and runs the Worker's ReAct
loop independently of the parent Supervisor (which parks on the ThreadGate).
On completion it writes the outcome back into ``state``; the session
done_callback wakes the gate so the parent Supervisor can aggregate.

Since docs/worker-delegation-design.md Phase A, the Worker can also SPLIT its own
mission mid-execution: calling ``route_to(subtasks=[...])`` (the unified delegation
entry) produces a spawn intent; the rollout spawns the parallel subagents (isolated
run parent ``<thread_id>-split``), waits for all of them, aggregates the results
back into its state, and keeps looping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import select

from app.core.engine.loop import merge_state_update
from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.routers import RoutingTarget, route_worker_by_outcome
from app.core.exceptions import (
    AgentA2AInterruptException,
    AgentCancelledException,
    AgentHumanInterruptException,
)

logger = logging.getLogger(__name__)

_SPLIT_WAIT_TIMEOUT = 600.0
_SPLIT_POLL_INTERVAL = 2.0
_A2A_WAIT_TIMEOUT = 600.0


async def run_worker_rollout(
    state: Any,
    config: dict[str, Any],
    thread_id: str,
    max_steps: int = 100,
) -> str:
    """Execute the Worker ReAct loop until terminal outcome; return outcome string.

    Mutates *state* in place (shares the parent AgentState). Outcomes:
    ``done | failed | truncated | cancelled``.

    Phase B: when the Worker dispatches an A2A subtask (``AgentA2AInterruptException``),
    the loop does NOT terminate — it parks until the remote callback result is
    written to DB, reloads the state, and continues the mission.
    """
    from app.core.monitoring.activity import activity_monitor

    worker_node = WorkerNode()
    outcome = "failed"

    try:
        step_count = 0
        while step_count < max_steps:
            step_count += 1
            await activity_monitor.check_cancellation(thread_id)

            try:
                update = await worker_node(state, config)
            except AgentA2AInterruptException:
                # Worker 发起 A2A：挂起等回调 → 重载 state → 继续 ReAct。
                state = await _wait_a2a_callback_then_reload(state, config, thread_id)
                if state is None:
                    outcome = "interrupted"
                    break
                continue
            except AgentHumanInterruptException as e:
                # 普通 HITL（敏感文件批准等）：请求已注册，由 session 主循环
                # 感知并挂起等待批准（_hang_for_resume）。
                outcome = "interrupted"
                logger.info(f"[WorkerRollout] {thread_id} interrupted (HITL): {e}")
                break
            merge_state_update(state, update)

            # Multi-skill sequential workflow delegated by Worker.
            if update.next_node == "sequential_workflow":
                from app.core.engine.nodes.sequential_workflow import SequentialWorkflowNode

                seq_update = await SequentialWorkflowNode()(state, config)
                merge_state_update(state, seq_update)

            # Worker mid-execution split: route_to(subtasks=...) →
            # SpawnSubagentsSignal → handle_spawn_subagents sets next_node=SPAWN_SUBAGENTS.
            if state.next_node == RoutingTarget.SPAWN_SUBAGENTS:
                await _run_worker_split(state, config, thread_id)
                continue

            next_node = route_worker_by_outcome(state)
            worker_outcome = state.worker_outcome or ""

            if next_node == "finish":
                # 成功→finish（是否审计由 Finish/AuditService 按 needs_audit 判定）。
                # needs_audit=true 时 session 主循环依据 state.ticket.needs_audit 重进图跑验收。
                outcome = "done" if worker_outcome in ("completed", "success") else (
                    "failed" if worker_outcome in ("truncated", "failed", "error") else "done"
                )
                break
            if next_node == "supervisor":
                outcome = "failed"
                break
            # Otherwise keep looping (rare; worker usually resolves in one call).
        else:
            outcome = "truncated"
    except AgentCancelledException:
        outcome = "cancelled"
        logger.info(f"[WorkerRollout] {thread_id} cancelled")
    except AgentHumanInterruptException as e:
        # 兜底：split/sequential 等其它执行段抛出的 HITL（Worker 本体已在上层 try 处理）。
        outcome = "interrupted"
        logger.info(f"[WorkerRollout] {thread_id} interrupted (HITL): {e}")
    except asyncio.CancelledError:
        # 主动取消（session._cancel_rollout）：不传播，让聚合轮能看到 outcome=cancelled。
        outcome = "cancelled"
        logger.info(f"[WorkerRollout] {thread_id} task cancelled")
    except Exception as e:
        outcome = "failed"
        logger.error(f"[WorkerRollout] {thread_id} failed: {e}", exc_info=True)

    logger.info(f"[WorkerRollout] {thread_id} finished with outcome={outcome}")
    return outcome


async def _wait_a2a_callback_then_reload(state: Any, config: dict, thread_id: str) -> Any | None:
    """Park the Worker until the remote A2A callback result is in DB, then reload state.

    The callback handler resolves the wait AFTER ``update_content_by_tool_call_id``
    persists the result, so the reloaded Worker sees it. On timeout a timeout
    result is written instead, so the Worker can report the failure rather than
    hang forever. Returns the reloaded state, or None if reload failed.
    """
    from app.core.engine.worker_registry import clear_a2a_wait, register_a2a_wait

    logger.info(f"[WorkerRollout] {thread_id} dispatched A2A; waiting for remote callback")
    event = register_a2a_wait(thread_id)
    try:
        try:
            await asyncio.wait_for(event.wait(), timeout=_A2A_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[WorkerRollout] {thread_id} A2A callback timed out")
            await _write_a2a_timeout_result(thread_id)
    finally:
        clear_a2a_wait(thread_id)
    return await _reload_worker_state(state, config, thread_id)


async def _reload_worker_state(state: Any, config: dict, thread_id: str) -> Any | None:
    """Rebuild AgentState from DB (the A2A result lives in the persisted tool message),
    preserving the Worker's mission ticket/goal so it can continue its ReAct loop."""
    from app.core.engine.background_agent.models import BackgroundAgentInputs
    from app.core.engine.runner_base import build_agent_state

    cf = config.get("configurable", {}) or {}
    try:
        inputs = BackgroundAgentInputs(
            goal=state.session_goal or (state.ticket.topic if state.ticket else "") or "",
            session_goal=state.session_goal,
            project_id=cf.get("project_id"),
            model=cf.get("model"),
            working_directory=cf.get("working_directory"),
            ticket=state.ticket,
            metadata=config.get("metadata", {}) or {},
        )
        return await build_agent_state(thread_id, inputs)
    except Exception as e:
        logger.exception(f"[WorkerRollout] {thread_id} failed to reload state after A2A: {e}")
        return None


async def _write_a2a_timeout_result(thread_id: str) -> None:
    """Mark the pending send_agent_task tool message as timed out in DB.

    The reloaded Worker then sees the failure and reports it instead of hanging
    on a silent missing callback. Also publishes the public A2A timeout
    lifecycle event (frontend panel).
    """
    from app.core.engine.message.repository import MessageRepository
    from app.core.monitoring.activity import activity_monitor
    from app.infrastructure.database import session_scope
    from app.models import Message

    # 读取挂起 human_request（含 task_id / target_device_key）用于发布事件。
    task_id = ""
    target_device_key = ""
    try:
        activity = await activity_monitor.get_activity(thread_id)
        hr = getattr(activity, "human_request", None) if activity else None
        if isinstance(hr, dict):
            payload = hr.get("payload") or {}
            task_id = str(payload.get("task_id") or "")
            target_device_key = str(payload.get("target_device_key") or "")
    except Exception as e:
        logger.warning(f"[WorkerRollout] Failed to read pending a2a payload: {e}", exc_info=True)

    from app.core.events.publishers import publish_a2a_lifecycle

    await publish_a2a_lifecycle(
        thread_id=thread_id,
        task_id=task_id,
        target_device_key=target_device_key,
        status="timeout",
        error=f"timeout after {_A2A_WAIT_TIMEOUT}s (no callback)",
    )

    await activity_monitor.clear_human_request(thread_id)

    async with session_scope() as session:
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_id, Message.role == "ai")
            .order_by(Message.sequence_number.desc())
            .limit(5)
        )
        rows = (await session.execute(stmt)).scalars().all()
    for msg in rows:
        if not msg.tool_calls:
            continue
        for tc in msg.tool_calls:
            if tc.get("name") in ("send_agent_task", "SendAgentTaskTool"):
                payload = {
                    "status": "failed",
                    "error": f"timeout after {_A2A_WAIT_TIMEOUT}s (no callback)",
                    "summary": "A2A subtask timed out",
                }
                repo = MessageRepository(thread_id)
                await repo.update_content_by_tool_call_id(
                    str(tc.get("id")), json.dumps(payload, ensure_ascii=False)
                )
                return


async def _run_worker_split(state: Any, config: dict, thread_id: str) -> None:
    """Worker 裂变：spawn → 等待全部 subagent → 聚合写回 state → 继续。

    subagent 的 run parent 为 ``<thread_id>-split``（与会话隔离），完成事件不会
    唤醒会话 Supervisor；Worker 在此轮询 SubagentRun 直到全部终态。
    """
    from app.core.engine.nodes.spawn_subagents import SpawnSubagentsNode

    logger.info(f"[WorkerRollout] {thread_id} splitting into subagents")
    # 统一 route_to 委派后，split 模式由 Worker 侧标记（区别于 Supervisor 裂变）：
    # spawn 节点据此隔离 run parent（<tid>-split）且不设 pending_aggregation。
    if isinstance(state.subagent_plan, dict):
        state.subagent_plan["split_mode"] = True
    plan = dict(state.subagent_plan or {})
    run_parent = f"{thread_id}-split"
    expected = len(plan.get("subtasks", []))

    # 1. Spawn（复用图节点；split 模式已隔离 run parent、不设 pending_aggregation）。
    spawn_update = await SpawnSubagentsNode()(state, config)
    merge_state_update(state, spawn_update)

    # 2. 等待全部 subagent 终态（轮询 SubagentRun，独立于会话 gate）。
    deadline = time.monotonic() + _SPLIT_WAIT_TIMEOUT
    while True:
        from app.core.monitoring.activity import activity_monitor

        await activity_monitor.check_cancellation(thread_id)
        statuses = await _split_subagent_statuses(run_parent)
        done = [s for s in statuses if s not in ("running", "awaiting_human", "awaiting_a2a")]
        if len(done) >= expected or time.monotonic() > deadline:
            break
        await asyncio.sleep(_SPLIT_POLL_INTERVAL)

    # 3. 聚合（复用 aggregate_results），写回 Worker state 供继续 ReAct。
    await _aggregate_split_into_state(state, run_parent, plan)

    # Worker 裂变后续跑：engine.run_node 不把 ReAct 对话写回 state.messages（信号
    # 分发路径的 StateUpdate 也不带 messages），聚合后 Worker 续跑会失去上下文
    # （message view 2->0 重新探索/二次裂变）。置 is_resuming 让 Worker 保留尾部
    # 会话（含聚合结果）继续写最终报告。
    if getattr(state, "ticket", None) is not None:
        state.ticket.is_resuming = True
        logger.info(f"[WorkerRollout] {thread_id} marked is_resuming after split aggregation")

    logger.info(
        f"[WorkerRollout] {thread_id} split done ({len(done)}/{expected} terminal); "
        f"resuming worker"
    )
    state.next_node = RoutingTarget.SUPERVISOR


async def _split_subagent_statuses(run_parent: str) -> list[str]:
    """Query terminal statuses of the split subagents (SubagentRun)."""
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.subagent import SubagentRun

    async with session_scope() as session:
        stmt = select(SubagentRun.status).where(SubagentRun.parent_thread_id == run_parent)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows)


async def _aggregate_split_into_state(state: Any, run_parent: str, plan: dict) -> None:
    """Load split subagent results, aggregate, and append the summary to Worker state."""
    from app.core.engine.message.native_classes import AIMessage
    from app.core.engine.nodes.aggregate_subagents import aggregate_results
    from app.infrastructure.database import session_scope
    from app.models.subagent import SubagentRun

    async with session_scope() as session:
        stmt = (
            select(SubagentRun)
            .where(SubagentRun.parent_thread_id == run_parent)
            .order_by(SubagentRun.started_at)
        )
        runs = (await session.execute(stmt)).scalars().all()

    results = [
        {
            "subagent_id": r.id,
            "status": r.status,
            "result": r.result or "",
        }
        for r in runs
    ]
    if not results:
        return

    aggregated = await aggregate_results(
        results,
        plan.get("aggregation_strategy", "merge"),
        plan.get("parent_task", ""),
    )
    agg_msg = AIMessage(content=aggregated)
    state.messages = list(state.messages or []) + [agg_msg]
    state.last_aggregation_result = aggregated
    logger.info(f"[WorkerRollout] Aggregated {len(results)} split results into state")
