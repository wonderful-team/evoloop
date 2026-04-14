"""
Subtask Aggregation Node - Phase 1

Collects and aggregates results from parallel subtask executions.
"""
import logging

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.tools.orchestration import aggregate_results

logger = logging.getLogger(__name__)


async def aggregator_node(state: AgentState, config: RunnableConfig) -> StateUpdate:
    """
    Subtask Aggregator — Joins parallel results (Phase 4).
    """
    blackboard = state.blackboard
    subtask_results = blackboard.subtask_results if blackboard else []
    pending_agg = blackboard.pending_aggregation if blackboard else None

    if not pending_agg:
        logger.warning("[Aggregator] No pending aggregation found")
        return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

    strategy = pending_agg.strategy or "merge"
    logger.info(f"[Aggregator] 🧩 Aggregating {len(subtask_results)} results with strategy '{strategy}'")

    try:
        # Call the aggregation tool
        agg_result = await aggregate_results(
            aggregation_strategy=strategy,
            results=subtask_results,
            original_task=pending_agg.parent_task or ""
        )

        # 4. Success Signal
        result_text = agg_result.aggregated if agg_result else "Aggregation failed"

        # 5. Update Blackboard (Clear all orchestration state + Save result)
        if blackboard:
            blackboard.subtask_results = []
            blackboard.pending_aggregation = None
            blackboard.spawn_plan = None
            blackboard.worker_outcome = "success"
            if not blackboard.metadata:
                from app.core.engine.state.blackboard import BlackboardMetadata
                blackboard.metadata = BlackboardMetadata()
            blackboard.metadata.last_aggregation_result = result_text

        return StateUpdate(
            messages=[AIMessage(content=f"Aggregation complete. Strategy: {strategy}. Total results: {len(subtask_results)}.")],
            next_node=RoutingTarget.SUPERVISOR,
            blackboard=blackboard
        )

    except Exception as e:
        logger.error(f"[Aggregator] Aggregation failed: {e}")
        # Ensure blackboard is returned even on error, potentially clearing pending state
        if blackboard:
            blackboard.subtask_results = []
            blackboard.pending_aggregation = None
            blackboard.spawn_plan = None
            blackboard.worker_outcome = "failed"
            if not blackboard.metadata:
                from app.core.engine.state.blackboard import BlackboardMetadata
                blackboard.metadata = BlackboardMetadata()
            blackboard.metadata.last_aggregation_result = f"Aggregation failed: {e}"
        return StateUpdate(
            messages=[AIMessage(
                content=f"Aggregation failed: {e}",
                metadata={"is_error": True, "error_type": "aggregation_failed"}
            )],
            next_node=RoutingTarget.SUPERVISOR,
            blackboard=blackboard
        )
