"""Shared agent execution loop — the native graph runner core."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.engine.state import AgentState, StateUpdate

logger = logging.getLogger(__name__)


def merge_state_update(state: "AgentState", update: "StateUpdate") -> None:
    """Merge a StateUpdate's explicitly-set fields back into the live AgentState.

    Uses ``update.model_fields_set`` so that fields defaulted by validators
    (not explicitly set by the node) are not copied — preventing accidental
    overwrites of existing state with default values.
    """
    for k in update.model_fields_set:
        setattr(state, k, getattr(update, k))


async def run_node_loop(
    state,
    config: dict,
    thread_id: str,
    *,
    max_loop_steps: int = 100,
    log_prefix: str = "Agent",
) -> None:
    """Execute the agent node loop until END or max steps.

    Mutates *state* in place — sets ``state.next_node`` at each iteration.
    Raises ``AgentCancelledException`` / ``AgentHumanInterruptException``
    if the activity monitor signals cancellation or HITL interrupt.
    """
    from app.core.engine.nodes.finish import FinishNode
    from app.core.engine.nodes.sequential_workflow import SequentialWorkflowNode
    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.routers import (
        RoutingTarget,
        route_finish,
        route_supervisor,
        route_worker_by_outcome,
    )
    from app.core.monitoring.activity import activity_monitor

    supervisor_node = SupervisorNode()
    worker_node = WorkerNode()
    finish_node = FinishNode()
    sequential_workflow_node = SequentialWorkflowNode()

    step_count = 0

    while state.next_node != RoutingTarget.END and step_count < max_loop_steps:
        step_count += 1
        current_node = state.next_node
        logger.info(f"[{log_prefix}] Transitioning to node: {current_node}")

        await activity_monitor.check_cancellation(thread_id)

        if current_node == RoutingTarget.SUPERVISOR:
            update = await supervisor_node(state, config)
            merge_state_update(state, update)
            state.next_node = route_supervisor(state)
            NEW_COMMAND_NODES = {
                RoutingTarget.WORKER,
                RoutingTarget.SEQUENTIAL_WORKFLOW,
            }
            if state.next_node in NEW_COMMAND_NODES:
                from app.core.engine.worker_registry import worker_registry
                old_task = await worker_registry.pop_previous_task(thread_id)
                if old_task and not old_task.done():
                    logger.info(f"[{log_prefix}] NEW_COMMAND target '{state.next_node}' detected. Cancelling old worker task.")
                    old_task.cancel()
        elif current_node == RoutingTarget.WORKER:
            update = await worker_node(state, config)
            merge_state_update(state, update)
            state.next_node = route_worker_by_outcome(state)
        elif current_node == RoutingTarget.FINISH:
            update = await finish_node(state, config)
            merge_state_update(state, update)
            state.next_node = route_finish(state)
        elif current_node == RoutingTarget.SEQUENTIAL_WORKFLOW:
            update = await sequential_workflow_node(state, config)
            merge_state_update(state, update)
            if not state.next_node or state.next_node == RoutingTarget.SEQUENTIAL_WORKFLOW:
                state.next_node = RoutingTarget.SUPERVISOR
        else:
            # Unknown node (e.g. legacy "chat" signal) → route to Supervisor for graceful handling
            logger.warning(f"[{log_prefix}] Unknown node {current_node}, routing to Supervisor.")
            state.next_node = RoutingTarget.SUPERVISOR

    if state.next_node != RoutingTarget.END and step_count >= max_loop_steps:
        logger.warning(f"[{log_prefix}] Hit max_loop_steps ({max_loop_steps}) for thread {thread_id}")
