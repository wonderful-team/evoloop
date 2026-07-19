"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import logging
from enum import Enum

from app.core.config import settings
from app.core.engine.state import AgentState
from app.core.engine.subtask_spawner import build_subtask_sends

logger = logging.getLogger(__name__)


class RoutingTarget(str, Enum):
    """Supported routing targets for the agent system."""
    OPERATOR = "operator"
    DEEP_RESEARCHER = "deep_researcher"
    DOCUMENTER = "documenter"
    FINISH = "finish"
    WORKER = "worker"
    FLASH_BRAIN = "flash_brain"
    SUPERVISOR = "supervisor"
    AGGREGATOR = "aggregator"
    SPAWN_SUBTASKS = "spawn_subtasks"
    SEQUENTIAL_WORKFLOW = "sequential_workflow"
    END = "END"


def route_by_next_node(state: AgentState) -> str:
    """Pure mapper: reads state.next_node, falls back to finish."""
    return state.next_node or "finish"


def route_worker_by_outcome(state: AgentState) -> str:
    """Worker 的路由由执行结果决定，LLM 不参与。"""
    outcome = state.worker_outcome
    if outcome in ("truncated", "failed", "error"):
        return "supervisor"
    return "finish"


def route_supervisor(state: AgentState) -> str:
    """
    Decides the next node after Supervisor.

    Returns a routing target node name (chat, worker, finish, ...).
    """
    next_node = state.next_node

    # --- Resource Constraints Enforcement ---
    iteration_count = (state.iteration_count or 0)
    max_steps = settings.SUPERVISOR_AGENT_MAX_STEPS
    if state.max_supervisor_steps:
        max_steps = state.max_supervisor_steps
    # ONLY enforce max_steps if there are no pending signals in the queue
    if iteration_count >= max_steps and not state.pending_signals:
        logger.warning(f"[Router] Hard limit reached ({iteration_count}/{max_steps}). Forcing termination.")
        return RoutingTarget.FINISH

    # --- Dynamic Subtask Spawning (State Driven) ---
    spawn_plan = state.spawn_plan
    if spawn_plan and spawn_plan.subtasks:
        return build_subtask_sends(state)

    # --- Routing Topology Whitelist ---
    # These nodes can be reached directly from Supervisor without an execution ticket wrapper
    if next_node:
        terminal_targets = {
            RoutingTarget.FINISH,
            RoutingTarget.SUPERVISOR,
            RoutingTarget.AGGREGATOR,
            RoutingTarget.SPAWN_SUBTASKS,
            RoutingTarget.SEQUENTIAL_WORKFLOW,
            RoutingTarget.END,
        }

        if next_node in terminal_targets:
            return next_node

        # If it's an intelligent target (not in terminal_targets), it MUST be handled by worker
        logger.info(f"[Router] Remapping intelligent target '{next_node}' -> 'worker'")

        # Verify ticket exists in state before routing to worker
        if not state.ticket:
            raise ValueError(
                f"Supervisor routing error: No execution ticket found for target '{next_node}'. "
                "Supervisor must call route_to() with a valid execution_ticket before routing to Worker."
            )
        return RoutingTarget.WORKER

    return "finish"


def route_finish(state: AgentState) -> str:
    """Decides the next node after Finish."""
    # Respect explicit supervisor routing (e.g. from Worker truncation recovery)
    if state.next_node == RoutingTarget.SUPERVISOR:
        logger.info("[Router] Finish routing back to Supervisor (truncation recovery or explicit signal).")
        return RoutingTarget.SUPERVISOR
    # If FinishNode explicitly set next_node to END, respect its decision even if
    # blocked_by_hook is still True from a previous turn (prevents infinite loops
    # when Supervisor -> Chat -> Finish re-enters Finish after a historic block).
    if state.next_node == RoutingTarget.END:
        return RoutingTarget.END
    if state.blocked_by_hook:
        logger.info("[Router] Finish blocked by hook. Looping back to supervisor.")
        return RoutingTarget.SUPERVISOR
    # Respect audit outcome — INCOMPLETE forces loopback to Supervisor
    if state.final_outcome:
        if state.final_outcome.upper() == "INCOMPLETE":
            logger.info("[Router] Finish audit: INCOMPLETE. Looping back to supervisor.")
            return RoutingTarget.SUPERVISOR
    return RoutingTarget.END
