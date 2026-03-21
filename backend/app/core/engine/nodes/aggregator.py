"""
Subtask Aggregation Node - Phase 1

Collects and aggregates results from parallel subtask executions.
"""
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.engine.tools.orchestration import aggregate_results
from app.constants import RoutingTarget

logger = logging.getLogger(__name__)


async def aggregator_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Subtask Aggregator — Joins parallel results (Phase 4).
    """
    blackboard = state.get("blackboard") or {}
    subtask_results = blackboard.get("subtask_results", [])
    pending_agg = blackboard.get("pending_aggregation", {})

    if not pending_agg:
        logger.warning("[Aggregator] No pending aggregation found")
        return {"next_node": RoutingTarget.SUPERVISOR}

    strategy = pending_agg.get("strategy", "merge")
    logger.info(f"[Aggregator] 🧩 Aggregating {len(subtask_results)} results with strategy '{strategy}'")

    try:
        # Call the aggregation tool
        agg_result = await aggregate_results(
            aggregation_strategy=strategy,
            results=subtask_results,
            original_task=pending_agg.get("parent_task", "")
        )

        # 4. Success Signal
        result_text = agg_result.get("aggregated", "Aggregation failed")
        
        # 5. Update Blackboard (Clear all orchestration state + Save result)
        blackboard["subtask_results"] = []
        blackboard["pending_aggregation"] = None
        blackboard["spawn_plan"] = None
        blackboard["worker_outcome"] = "success"
        blackboard.setdefault("metadata", {})["last_aggregation_result"] = result_text

        return {
            "messages": [AIMessage(content=f"Aggregation complete. Strategy: {strategy}. Total results: {len(subtask_results)}.")],
            "next_node": RoutingTarget.SUPERVISOR,
            "blackboard": blackboard
        }

    except Exception as e:
        logger.error(f"[Aggregator] Aggregation failed: {e}")
        # Ensure blackboard is returned even on error, potentially clearing pending state
        blackboard["subtask_results"] = []
        blackboard["pending_aggregation"] = None
        blackboard["spawn_plan"] = None
        blackboard["worker_outcome"] = "failed"
        blackboard.setdefault("metadata", {})["last_aggregation_result"] = f"Aggregation failed: {e}"
        return {
            "messages": [AIMessage(content=f"Aggregation failed: {e}")],
            "next_node": RoutingTarget.SUPERVISOR,
            "blackboard": blackboard
        }
