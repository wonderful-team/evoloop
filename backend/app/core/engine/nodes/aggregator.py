"""
Subtask Aggregation Node - Phase 1

Collects and aggregates results from parallel subtask executions.
"""
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.engine.tools.planning import aggregate_results

logger = logging.getLogger(__name__)


async def aggregator_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Aggregates results from completed subtasks.

    Triggered when all parallel subtasks have completed.
    Uses the aggregation strategy specified in the original plan.
    """
    scratchpad = state.get("scratchpad", {})
    subtask_results = scratchpad.get("subtask_results", [])
    pending_agg = scratchpad.get("_pending_aggregation", {})

    if not subtask_results:
        logger.warning("[Aggregator] No subtask results found")
        return {
            "messages": [AIMessage(content="⚠️ No subtask results to aggregate")],
            "next_node": "supervisor"
        }

    strategy = pending_agg.get("strategy", "merge")
    parent_task = pending_agg.get("parent_task", "Unknown task")

    logger.info(f"[Aggregator] Aggregating {len(subtask_results)} subtask results with strategy '{strategy}'")

    try:
        # Call the aggregation tool
        agg_result = await aggregate_results(
            aggregation_strategy=strategy,
            results=subtask_results,
            original_task=parent_task
        )

        aggregated = agg_result.get("aggregated", "")

        # Clear aggregation state
        new_scratchpad = {
            **scratchpad,
            "subtask_results": [],  # Clear collected results
            "_pending_aggregation": None,  # Clear pending state
            "_last_aggregation": {
                "strategy": strategy,
                "subtask_count": len(subtask_results),
                "result_preview": str(aggregated)[:200] if aggregated else ""
            }
        }

        logger.info(f"[Aggregator] Aggregation complete. Result length: {len(str(aggregated))}")

        return {
            "messages": [AIMessage(content=f"📊 **Task Aggregation Complete**\n\n{aggregated}")],
            "scratchpad": new_scratchpad,
            "next_node": "supervisor"
        }

    except Exception as e:
        logger.error(f"[Aggregator] Aggregation failed: {e}")
        return {
            "messages": [AIMessage(content=f"❌ Aggregation failed: {e}")],
            "next_node": "supervisor"
        }
