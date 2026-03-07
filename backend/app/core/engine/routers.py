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
