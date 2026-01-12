from langgraph.constants import Send

from app.core.engine.state import AgentState


def route_supervisor(state: AgentState):
    """
    Decides the next node after Supervisor.
    Supports parallel research dispatch via Send().
    """
    next_node = state["next_node"]
    if next_node == "map_research":
        tasks = state.get("parallel_research_tasks", [])
        project_id = state.get("project_id", 1)
        # Pass full context needed for research
        return [Send("deep_researcher", {
            "research_topic": topic,
            "project_id": project_id,
        }) for topic in tasks]
    if next_node == "finish":
        return "finish"
    return next_node

def route_tester(state: AgentState):
    """
    Decides next node based on test results (Pass/Fail) and retry count.
    """
    if state.get("test_results") == "PASS":
        return "supervisor"  # Let supervisor decide if we are done
    else:
        # Simple retry logic: if fail, go back to coder
        # In V3 advanced, we might go back to researcher or supervisor
        if state.get("iteration_count", 0) > 3:
            return "meta_reviewer"  # Intervention!
        return "coder"

def route_by_next_node_field(state: AgentState):
    """
    Generic router that simply returns state["next_node"].
    Used by 'router', 'deep_researcher', etc.
    """
    return state["next_node"]

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

def make_expression_router(conditions: list[dict[str, str]], default: str) -> Callable[[AgentState], str]:
    """
    Factory that creates a router function based on a list of expression conditions.
    
    Args:
        conditions: List of dicts, e.g. [{"expr": "state['scratchpad']['score'] > 5", "to": "finish"}]
        default: Fallback node if no conditions match.
    """
    def expression_router(state: AgentState) -> str:
        # Prepare evaluation context
        # We provide 'state' and 'scratchpad' for convenience
        scratchpad = state.get("scratchpad", {})
        eval_context = {
            "state": state,
            "scratchpad": scratchpad,
            "len": len,
            "int": int,
            "str": str,
            "bool": bool
        }

        for case in conditions:
            expr = case.get("expr")
            to_node = case.get("to")

            try:
                # Basic safety: Ensure expression is reasonably short and doesn't contain unsafe keywords
                # Note: This is NOT a secure sandbox. Do not run untrusted configs.
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
