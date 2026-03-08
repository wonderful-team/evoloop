"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import logging
from collections.abc import Callable

from langgraph.types import Send

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


def route_supervisor(state: AgentState) -> str | list[Send]:
    """
    Decides the next node after Supervisor.

    Supports:
    - Standard single-node routing
    - Dynamic parallel subtask spawning (Phase 1)
    """
    next_node = state.get("next_node")

    # --- 🏅 Phase 1: Dynamic Subtask Spawning ---
    # Check if Supervisor generated a spawn plan (from decompose_task tool)
    spawn_plan = state.get("scratchpad", {}).get("_spawn_plan")
    if spawn_plan and spawn_plan.get("subtasks"):
        subtasks = spawn_plan["subtasks"]
        project_id = state.get("project_id", 1)
        parent_thread_id = state.get("thread_id", "unknown")

        logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

        # Create Send commands for parallel execution
        # Each subtask becomes a Worker execution with its own ticket
        sends = []
        for i, subtask in enumerate(subtasks):
            # Build system instructions with skill hint if available
            skill_hint = subtask.get("skill_hint") or spawn_plan.get("suggested_skill")
            system_instructions = f"Execute subtask: {subtask['intent']}"
            if skill_hint:
                system_instructions += f"\n\n💡 HINT: This subtask may be accomplished using the learned skill '{skill_hint}'. Try `search_skills` first, and if found with execution_mode='deterministic', use `run_macro` for optimal performance."

            ticket = {
                "ticket_type": "subtask",
                "topic": subtask["intent"],
                "parent_task_id": parent_thread_id,
                "subtask_id": subtask.get("id", f"subtask_{i}"),
                "agent_config": {
                    "role_name": f"Subtask-{subtask.get('id', i)}",
                    "system_instructions": system_instructions,
                    "tools": subtask.get("tools", []),
                    "is_subtask": True,
                    "subtask_context": subtask.get("context", {}),
                    "skill_hint": skill_hint,  # May be used by Worker
                },
                "parameters": {
                    "estimated_complexity": subtask.get("estimated_complexity", "medium"),
                    "depends_on": subtask.get("depends_on", []),
                }
            }

            sends.append(Send("worker", {
                "project_id": project_id,
                "execution_ticket": ticket,
                "is_subtask": True,
            }))

        # Store aggregation requirements for later
        if spawn_plan.get("_requires_aggregation"):
            state["scratchpad"]["_pending_aggregation"] = {
                "strategy": spawn_plan.get("aggregation_strategy", "merge"),
                "expected_count": len(subtasks),
                "parent_task": spawn_plan.get("parent_task", ""),
            }

        return sends

    # --- 🏅 Unified Cognitive Routing (v5.0) ---
    # The Supervisor now decides the "expertise" dynamically via agent_config.
    # The Graph is flattened: Specialized subgraphs are replaced by Universal Workers.

    # 1. Known Terminal/Structural Nodes
    terminal_nodes = ("chat", "finish", "flash_brain", "supervisor")
    if next_node in terminal_nodes:
        return next_node

    # 2. Universal Remapping
    # Any other target (legacy SOPs, hallucinated roles) is handled by the Worker hub.
    # SupervisorNode ensures agent_config is hydrated for these targets.
    if next_node:
        logger.info(f"[Router] Remapping intelligent target '{next_node}' -> 'worker'")
        return "worker"

    return "finish"


def route_by_next_node_field(state: AgentState):
    """
    Generic router that simply returns state["next_node"].
    """
    return state.get("next_node", "supervisor")


def make_expression_router(conditions: list[dict[str, str]], default: str) -> Callable[[AgentState], str]:
    """
    Factory that creates a router function based on a list of expression conditions.
    """

    def expression_router(state: AgentState) -> str:
        # Prepare evaluation context
        scratchpad = state.get("scratchpad", {})
        eval_context = {
            "state": state,
            "scratchpad": scratchpad,
            "len": len,
            "int": int,
            "str": str,
            "bool": bool,
        }

        for case in conditions:
            expr = case.get("expr")
            to_node = case.get("to")

            try:
                # Basic safety
                if "import" in expr or "__" in expr:
                    logger.warning(f"Unsafe expression detected and skipped: {expr}")
                    continue

                result = eval(expr, {"__builtins__": {}}, eval_context)
                if result:
                    logger.info(f"Router Expression '{expr}' matched. Routing to {to_node}")
                    return to_node
            except Exception as e:
                logger.error(f"Error evaluating expression '{expr}': {e}")

        logger.info(f"No expressions matched. Routing to default: {default}")
        return default

    return expression_router
