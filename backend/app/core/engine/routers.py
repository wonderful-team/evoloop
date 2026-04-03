"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import logging
from collections.abc import Callable

from langgraph.types import Send
from langchain_core.messages import HumanMessage

from app.constants import DEFAULT_PROJECT_ID, RoutingTarget
from app.core.config import settings
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


def route_supervisor(state: AgentState) -> str | list[Send]:
    """
    Decides the next node after Supervisor.
    """
    next_node = state.get("next_node")
    blackboard = state.get("blackboard", {})

    # --- Phase 5: Resource Constraints Enforcement ---
    iteration_count = state.get("iteration_count", 0)
    if iteration_count >= settings.SUPERVISOR_AGENT_MAX_STEPS:
        logger.warning(f"[Router] Hard limit reached ({iteration_count}/{settings.SUPERVISOR_AGENT_MAX_STEPS}). Forcing termination.")
        return RoutingTarget.FINISH

    # --- 🏅 Phase 4: Dynamic Subtask Spawning (Blackboard Driven) ---
    spawn_plan = blackboard.get("spawn_plan")
    if spawn_plan and spawn_plan.get("subtasks"):
        subtasks = spawn_plan["subtasks"]
        project_id = state.get("project_id", DEFAULT_PROJECT_ID)
        parent_thread_id = state.get("thread_id", "unknown")

        logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

        sends = []
        for i, subtask in enumerate(subtasks):
            subtask_id = subtask.get("id", f"subtask_{i}")
            # [CRITICAL Phase 5] Scoped Identity for concurrency safety
            scoped_thread_id = f"{parent_thread_id}:sub:{subtask_id}"
            
            skill_hint = subtask.get("skill_hint") or spawn_plan.get("suggested_skill")
            # Refined professional instructions for subtasks
            system_instructions = "Analyze the mission goal and execute the necessary tools effectively."
            if skill_hint:
                system_instructions += f" Use learned skill: {skill_hint}."

            # Get tools from subtask, but ensure it's not empty
            subtask_tools = subtask.get("tools", [])
            # If no tools specified, allow all worker tools by not setting the field
            # (ToolManager will use full tool set when dynamic_tools is falsy)
            agent_config = {
                "role_name": f"Field Specialist {subtask_id}",
                "system_instructions": system_instructions,
                "is_subtask": True,
                "subtask_context": subtask.get("context", {}),
                "skill_hint": skill_hint,
            }
            # Only set tools if explicitly provided and non-empty
            if subtask_tools:
                agent_config["tools"] = subtask_tools
                logger.info(f"[Router] Subtask {subtask_id} assigned tools: {subtask_tools}")
            else:
                logger.info(f"[Router] Subtask {subtask_id} using full worker tool set")

            # Build rich context for subtask execution
            # Include description as acceptance criteria and context as parameters
            subtask_acceptance_criteria = []
            if subtask.get("description"):
                subtask_acceptance_criteria.append(subtask["description"])
            if subtask.get("title") and subtask["title"] != subtask["intent"]:
                subtask_acceptance_criteria.append(f"Task: {subtask['title']}")
            
            subtask_parameters = subtask.get("context", {})
            if subtask.get("dependencies"):
                subtask_parameters["dependencies"] = subtask["dependencies"]
            
            # Inherit historical context from parent task's execution_ticket (if available)
            parent_ticket = blackboard.get("ticket", {})
            
            ticket = {
                "ticket_type": "subtask",
                "topic": subtask["intent"],
                "parent_task_id": parent_thread_id,
                "subtask_id": subtask_id,
                "agent_config": agent_config,
                "acceptance_criteria": subtask_acceptance_criteria if subtask_acceptance_criteria else None,
                "parameters": subtask_parameters if subtask_parameters else None,
                # Inherit historical context from parent task for continuity
                "historical_context": parent_ticket.get("historical_context") if parent_ticket else None,
                "referenced_tech": parent_ticket.get("referenced_tech") if parent_ticket else None,
                # Note: MCP servers are NOT inherited by subtasks
                # Each subtask must explicitly request MCP servers via use_mcp_server
            }

            sends.append(Send(RoutingTarget.WORKER, {
                "project_id": project_id,
                "thread_id": scoped_thread_id, # Target isolation
                "execution_ticket": ticket,
                "blackboard": blackboard.copy(), # Context preservation (WD, Clipboard)
                "is_subtask": True,
                # [CRITICAL] Start with empty messages to prevent inheriting parent history
                # Worker will set the mission message via build_mission_message()
                "messages": [],
            }))

        # Consume the spawn_plan to prevent re-triggering on next router pass
        blackboard["spawn_plan"] = None

        return sends

    # ... Standard cognitive routing follows
    terminal_nodes = (RoutingTarget.CHAT, RoutingTarget.FINISH, RoutingTarget.SUPERVISOR)
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

        # CRITICAL: No execution ticket found - this indicates a Supervisor routing bug
        logger.error(f"[Router] CRITICAL: No execution ticket in blackboard for Worker route. "
                     f"This should not happen - Supervisor should always create a ticket via route_to.")
        raise ValueError(
            "Supervisor routing error: No execution ticket found. "
            "Supervisor must call route_to() with a valid execution_ticket before routing to Worker."
        )

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
