"""Worker rollout — standalone Worker ReAct loop (session-mode background execution).

A rollout shares the parent ``AgentState`` instance and runs the Worker's ReAct
loop independently of the parent Supervisor (which parks on the ThreadGate).
On completion it writes the outcome back into ``state``; the session
done_callback wakes the gate so the parent Supervisor can aggregate.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.engine.loop import merge_state_update
from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.routers import route_worker_by_outcome
from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException

logger = logging.getLogger(__name__)


async def run_worker_rollout(
    state: Any,
    config: dict[str, Any],
    thread_id: str,
    max_steps: int = 100,
) -> str:
    """Execute the Worker ReAct loop until terminal outcome; return outcome string.

    Mutates *state* in place (shares the parent AgentState). Outcomes:
    ``done | failed | truncated | cancelled``.
    """
    from app.core.monitoring.activity import activity_monitor

    worker_node = WorkerNode()
    outcome = "failed"

    try:
        step_count = 0
        while step_count < max_steps:
            step_count += 1
            await activity_monitor.check_cancellation(thread_id)

            update = await worker_node(state, config)
            merge_state_update(state, update)

            # Multi-skill sequential workflow delegated by Worker.
            if update.next_node == "sequential_workflow":
                from app.core.engine.nodes.sequential_workflow import (
                    SequentialWorkflowNode,
                )

                seq_update = await SequentialWorkflowNode()(state, config)
                merge_state_update(state, seq_update)

            next_node = route_worker_by_outcome(state)
            worker_outcome = state.worker_outcome or ""

            if next_node == "finish":
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
        # Worker 执行中遇到 HITL（敏感文件批准等）：HITL 请求已由
        # HITLOrchestrator 注册（DB/事件），此处不得当作崩溃。
        # 标记 outcome 后由 session 主循环感知并挂起等待批准（_hang_for_resume）。
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
