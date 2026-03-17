"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import logging
from collections.abc import Callable

from langgraph.types import Send

from app.constants import DEFAULT_PROJECT_ID, RoutingTarget
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


def route_supervisor(state: AgentState) -> str | list[Send]:
    """
    Decides the next node after Supervisor.
    """
    next_node = state.get("next_node")
    blackboard = state.get("blackboard", {})

    # --- 🏅 Phase 4: Dynamic Subtask Spawning (Blackboard Driven) ---
    spawn_plan = blackboard.get("spawn_plan")
    if spawn_plan and spawn_plan.get("subtasks"):
        subtasks = spawn_plan["subtasks"]
        project_id = state.get("project_id", DEFAULT_PROJECT_ID)
        parent_thread_id = state.get("thread_id", "unknown")

        logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

        sends = []
        for i, subtask in enumerate(subtasks):
            skill_hint = subtask.get("skill_hint") or spawn_plan.get("suggested_skill")
            system_instructions = f"Execute subtask: {subtask['intent']}"
            if skill_hint:
                system_instructions += f"\n\n💡 HINT: This subtask may be accomplished using the learned skill '{skill_hint}'."

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
                    "skill_hint": skill_hint,
                }
            }

            sends.append(Send(RoutingTarget.WORKER, {
                "project_id": project_id,
                "execution_ticket": ticket,
                "is_subtask": True,
            }))

        return sends

    # ... Standard cognitive routing follows
    terminal_nodes = (RoutingTarget.CHAT, RoutingTarget.FINISH, RoutingTarget.FLASH_BRAIN, RoutingTarget.SUPERVISOR)
    if next_node in terminal_nodes:
        return next_node

    if next_node:
        logger.info(f"[Router] Remapping intelligent target '{next_node}' -> 'worker'")

        # Extract execution_ticket from blackboard (set by SignalDispatcher)
        # and place it at state root for WorkerNode to access
        execution_ticket = blackboard.get("ticket")
        if execution_ticket:
            # Use Send to pass execution_ticket to worker
            return Send(RoutingTarget.WORKER, {
                "project_id": state.get("project_id", DEFAULT_PROJECT_ID),
                "execution_ticket": execution_ticket,
            })

        # Fallback: route without ticket (Worker will handle gracefully)
        return Send(RoutingTarget.WORKER, {
            "project_id": state.get("project_id", DEFAULT_PROJECT_ID),
            "execution_ticket": {
                "ticket_type": "task",
                "topic": "General execution",
                "agent_config": {
                    "role_name": next_node.replace("_", " ").title(),
                    "system_instructions": f"Execute as {next_node}",
                }
            },
        })

    return "finish"


def route_by_next_node_field(state: AgentState):
    return state.get("next_node", RoutingTarget.SUPERVISOR)


def make_expression_router(conditions: list[dict[str, str]], default: str) -> Callable[[AgentState], str]:
    def expression_router(state: AgentState) -> str:
        # Prepare evaluation context (Phase 4: Blackboard Only)
        blackboard = state.get("blackboard", {})
        eval_context = {
            "state": state,
            "blackboard": blackboard,
            "len": len,
            "int": int,
            "str": str,
            "bool": bool,
        }

        for case in conditions:
            expr = case.get("expr")
            to_node = case.get("to")

            try:
                if "import" in expr or "__" in expr:
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
