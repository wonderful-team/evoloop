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


class AggregatorNode:
    """Subtask Aggregator — Joins parallel results."""

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        blackboard = state.blackboard
        subtask_results = blackboard.subtask_results if blackboard else []
        pending_agg = blackboard.pending_aggregation if blackboard else None

        if not pending_agg:
            logger.warning("[Aggregator] No pending aggregation found")
            return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

        strategy = pending_agg.strategy or "merge"
        logger.info(f"[Aggregator] 🧩 Aggregating {len(subtask_results)} results with strategy '{strategy}'")

        result_text = ""
        worker_outcome = "success"
        is_error = False

        # Log pre-aggregation raw texts for auditing (no truncation applied)
        for i, r in enumerate(subtask_results):
            raw_text = str(getattr(r, "result", r))
            sid = getattr(r, "subtask_id", i)
            logger.info(f"[Aggregator] Pre-aggregate raw result [{i}] (subtask_id={sid}, length={len(raw_text)}):\n{raw_text}")

        try:
            # Normalize SubtaskResult objects to dicts for the tool schema
            raw_results = [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in subtask_results
            ]
            # Call the aggregation tool via ainvoke (aggregate_results is a StructuredTool)
            agg_result = await aggregate_results.ainvoke({
                "aggregation_strategy": strategy,
                "results": raw_results,
                "original_task": pending_agg.parent_task or ""
            })
            result_text = agg_result.aggregated if agg_result else "Aggregation failed"
            logger.info(f"[Aggregator] Post-aggregate result (length={len(result_text)}):\n{result_text}")
        except Exception as e:
            logger.error(f"[Aggregator] Aggregation failed: {e}")
            result_text = f"Aggregation failed: {e}"
            worker_outcome = "failed"
            is_error = True

        # Clear all orchestration state
        if blackboard:
            blackboard.subtask_results = []
            blackboard.pending_aggregation = None
            blackboard.spawn_plan = None
            blackboard.worker_outcome = worker_outcome
            if not blackboard.metadata:
                from app.core.engine.state.blackboard import BlackboardMetadata
                blackboard.metadata = BlackboardMetadata()
            blackboard.metadata.last_aggregation_result = result_text
            # Reset ticket so Supervisor does not treat itself as a subtask
            blackboard.ticket = None

        msg = AIMessage(
            content=f"Aggregation complete. Strategy: {strategy}. Total results: {len(subtask_results)}.",
            metadata={"is_error": is_error, "error_type": "aggregation_failed"} if is_error else None,
        )

        return StateUpdate(
            messages=[msg],
            next_node=RoutingTarget.SUPERVISOR,
            blackboard=blackboard,
            is_subtask=False,
        )
