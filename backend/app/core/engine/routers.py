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
    """
    next_node = state.get("next_node")

    # [Compatibility] Remap legacy targets if LLM hallucinates old node names
    if next_node in ["coder", "tester", "planner", "operator", "deep_researcher", "documenter"]:
        logger.info(f"[Router] Remapping legacy routing '{next_node}' -> 'worker'")
        return "worker"

    # Parallel Research (v5: each branch runs as a Worker with researcher persona)
    if next_node == "map_research":
        tasks = state.get("parallel_research_tasks", [])
        project_id = state.get("project_id", 1)
        return [Send("worker", {
            "research_topic": topic,
            "project_id": project_id,
            "execution_ticket": {
                "ticket_type": "web_research",
                "topic": topic,
                "agent_config": {
                    "role_name": "Deep Researcher",
                    "system_instructions": "You are an expert analyst. Conduct thorough research on the assigned topic.",
                    "tools": [],
                },
            },
        }) for topic in tasks]

    # Phase 4: Dynamic SOP Dispatcher
    intent_category = state.get("intent_category")
    
    # 1. Mobile
    if next_node == "mobile_exploration" or intent_category == "mobile_exploration":
        logger.info(f"[Router] Routing to Mobile Exploration SOP (Subgraph)")
        return "mobile_sop"
        
    # 2. Browser
    if next_node == "browser_navigation" or intent_category == "browser_navigation" or intent_category == "web_research":
        logger.info(f"[Router] Routing to Browser Navigation SOP (Subgraph)")
        return "browser_sop"
        
    # 3. Desktop
    if next_node == "desktop_automation" or intent_category == "desktop_automation":
        logger.info(f"[Router] Routing to Desktop Automation SOP (Subgraph)")
        return "desktop_sop"

    if next_node == "finish":
        return "finish"

    # Valid v5 nodes: worker, chat, flash_brain, finish (remapped via YAML edges)
    return next_node or "finish"


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
