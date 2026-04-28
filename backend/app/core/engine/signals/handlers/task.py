import logging

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.base import SignalHandler
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import BlackboardMetadata
from ..schemas import SpawnSubtasksSignal, TerminateSignal

logger = logging.getLogger(__name__)


class SpawnSubtasksHandler(SignalHandler[SpawnSubtasksSignal]):
    """Handler for SpawnSubtasksSignal."""

    async def handle(
        self, state: AgentState, signal: SpawnSubtasksSignal, config: RunnableConfig
    ) -> StateUpdate:
        spawn_plan = signal.plan
        logger.info(f"[SignalHandler] 🚀 Spawning {len(spawn_plan.subtasks or [])} parallel subtasks")

        blackboard = state.blackboard # Already guaranteed to be BlackboardState
        blackboard.spawn_plan = spawn_plan

        if spawn_plan.requires_aggregation:
            from app.core.engine.state.blackboard import PendingAggregation
            blackboard.pending_aggregation = PendingAggregation(
                strategy=spawn_plan.aggregation_strategy or "merge",
                expected_count=len(spawn_plan.subtasks or []),
                parent_task=spawn_plan.parent_task or "",
            )

        return StateUpdate(
            next_node=RoutingTarget.SPAWN_SUBTASKS,
            blackboard=blackboard
        )


class TerminateHandler(SignalHandler[TerminateSignal]):
    """Handler for TerminateSignal."""

    async def handle(
        self, state: AgentState, signal: TerminateSignal, config: RunnableConfig
    ) -> StateUpdate:
        logger.info(f"[SignalHandler] 🏁 Natural Termination Signal received. Outcome: {signal.outcome}")

        blackboard = state.blackboard
        blackboard.metadata = (blackboard.metadata or BlackboardMetadata()).model_copy(
            update={"shadow_audit": True, "termination_outcome": signal.outcome}
        )

        return StateUpdate(
            next_node=RoutingTarget.FINISH,
            blackboard=blackboard
        )
