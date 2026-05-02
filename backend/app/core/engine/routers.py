"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import logging
from enum import Enum

from langgraph.types import Send

from app.core.config import settings
from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.subtask_spawner import build_subtask_sends

logger = logging.getLogger(__name__)


class RoutingTarget(str, Enum):
    """Supported routing targets for the agent system."""
    OPERATOR = "operator"
    DEEP_RESEARCHER = "deep_researcher"
    DOCUMENTER = "documenter"
    CHAT = "chat"
    FINISH = "finish"
    WORKER = "worker"
    FLASH_BRAIN = "flash_brain"
    SUPERVISOR = "supervisor"
    AGGREGATOR = "aggregator"
    SPAWN_SUBTASKS = "spawn_subtasks"
    SEQUENTIAL_WORKFLOW = "sequential_workflow"
    END = "END"


def route_by_next_node(state: AgentState) -> str:
    """Generic router that follows state.next_node if set."""
    target = state.next_node
    if target:
        # Define the set of allowed targets for general conditional edges
        # mapping in agent_main.yaml. 
        allowed_targets = {
            RoutingTarget.SUPERVISOR,
            RoutingTarget.SEQUENTIAL_WORKFLOW,
            RoutingTarget.FINISH,
            RoutingTarget.END,
        }
        if target not in allowed_targets:
            logger.error(f"[Router] 🚨 Invalid next_node '{target}'. Not in YAML map. Falling back to supervisor.")
            return RoutingTarget.SUPERVISOR
            
        logger.info(f"[Router] Dynamic next_node: {target}")
        return target
    return RoutingTarget.SUPERVISOR


def route_supervisor(state: AgentState) -> str | list[Send]:
    """
    Decides the next node after Supervisor.

    Returns:
        * ``str`` — normal routing target (chat, worker, finish, ...).
        * ``list[Send]`` — **dynamic subgraph spawning**.  This is a LangGraph
          conditional-edge feature (not a regular node target).  When returned,
          LangGraph creates parallel Worker subgraphs for each ``Send``.  After
          all subgraphs complete, execution resumes at Supervisor.
    """
    next_node = state.next_node
    blackboard = BlackboardState.model_validate(state.blackboard) if state.blackboard else None
    if not blackboard:
        blackboard = BlackboardState()

    # --- Phase 5: Resource Constraints Enforcement ---
    iteration_count = (state.iteration_count or 0)
    if iteration_count >= settings.SUPERVISOR_AGENT_MAX_STEPS:
        logger.warning(f"[Router] Hard limit reached ({iteration_count}/{settings.SUPERVISOR_AGENT_MAX_STEPS}). Forcing termination.")
        return RoutingTarget.FINISH

    # --- Phase 4: Dynamic Subtask Spawning (Blackboard Driven) ---
    spawn_plan = blackboard.spawn_plan
    if spawn_plan and spawn_plan.subtasks:
        return build_subtask_sends(state, blackboard)

    # --- Phase 5: Routing Topology Whitelist ---
    # These nodes can be reached directly from Supervisor without an execution ticket wrapper
    terminal_nodes = (
        RoutingTarget.CHAT,
        RoutingTarget.FINISH,
        RoutingTarget.SUPERVISOR,
        RoutingTarget.AGGREGATOR,
        RoutingTarget.SPAWN_SUBTASKS,
        RoutingTarget.SEQUENTIAL_WORKFLOW,
    )
    if next_node:
        # Define the set of allowed terminal targets for the supervisor's conditional edge
        # mapping in agent_main.yaml. 
        terminal_targets = {
            RoutingTarget.CHAT,
            RoutingTarget.FINISH,
            RoutingTarget.SUPERVISOR,
            RoutingTarget.AGGREGATOR,
            RoutingTarget.SPAWN_SUBTASKS,
            RoutingTarget.SEQUENTIAL_WORKFLOW,
        }

        if next_node in terminal_targets:
            return next_node

        # If it's an intelligent target (not in terminal_targets), it MUST be handled by worker
        logger.info(f"[Router] Remapping intelligent target '{next_node}' -> 'worker'")
        
        # Verify ticket exists in blackboard (set by SignalDispatcher) before routing to worker
        if not blackboard.ticket:
            raise ValueError(
                f"Supervisor routing error: No execution ticket found for target '{next_node}'. "
                "Supervisor must call route_to() with a valid execution_ticket before routing to Worker."
            )
        return RoutingTarget.WORKER

    return "finish"


def route_finish(state: AgentState) -> str:
    """Decides the next node after Finish."""
    blackboard = state.blackboard
    # If FinishNode explicitly set next_node to END, respect its decision even if
    # blocked_by_hook is still True from a previous turn (prevents infinite loops
    # when Supervisor -> Chat -> Finish re-enters Finish after a historic block).
    if state.next_node == RoutingTarget.END:
        return RoutingTarget.END
    if blackboard and blackboard.metadata and blackboard.metadata.blocked_by_hook:
        logger.info("[Router] Finish blocked by hook. Looping back to supervisor.")
        return RoutingTarget.SUPERVISOR
    return RoutingTarget.END


# Backward-compatible re-export for expression-based routing
from app.core.engine.expression_evaluator import make_expression_router  # noqa: E402,F401
