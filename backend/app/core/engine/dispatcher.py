import copy
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals import RouteToSignal, RoutingContext, SpawnSubtasksSignal, TerminateSignal
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import BlackboardMetadata, BlackboardState
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    TicketParameters,
)

logger = logging.getLogger(__name__)


class SignalDispatcher:
    """
    Centralized dispatcher for AgentSignals (Phase 2).
    Translates architectural signals into Graph state transitions.
    """

    @staticmethod
    async def dispatch(state: AgentState, signal: Any, config: RunnableConfig) -> StateUpdate:
        """
        Dispatches the signal and returns the updated state for the next node.
        """
        if isinstance(signal, RouteToSignal):
            return await SignalDispatcher._handle_route_to(state, signal, config)
        elif isinstance(signal, SpawnSubtasksSignal):
            return await SignalDispatcher._handle_spawn_subtasks(state, signal, config)
        elif isinstance(signal, TerminateSignal):
            return await SignalDispatcher._handle_terminate(state, signal, config)

        logger.warning(f"[Dispatcher] Unknown signal type: {type(signal)}")
        return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

    @staticmethod
    async def _handle_route_to(state: AgentState, signal: RouteToSignal, config: RunnableConfig) -> StateUpdate:
        target = signal.target
        reason = signal.reason
        routing_context = signal.context
        authorized_tools = signal.authorized_tools

        logger.info(f"[Dispatcher] ✅ Routing to: {target} | Reason: {reason}")

        # 1. Update Blackboard (Phase 1 Pattern)
        blackboard = BlackboardState.model_validate(state.blackboard) if state.blackboard else BlackboardState()
        blackboard.route_reason = reason

        # 2. Construct Execution Ticket
        inferred_namespace = routing_context.namespace_context

        agent_config = routing_context.agent_config or AgentRuntimeConfig()
        if not agent_config.namespace_context:
            agent_config.namespace_context = inferred_namespace
        if not agent_config.role_name:
            agent_config.role_name = str(target).replace("_", " ").title()
        if authorized_tools is not None:
            agent_config.tools = authorized_tools

        parameters_fields = set(TicketParameters.model_fields.keys())
        parameters = {k: v for k, v in routing_context.model_dump().items() if k in parameters_fields}

        execution_ticket = ExecutionTicket(
            ticket_type=routing_context.ticket_type or "task",
            priority=routing_context.priority or "normal",
            focus_paths=routing_context.focus_paths or [],
            topic=routing_context.topic or routing_context.query or reason,
            acceptance_criteria=routing_context.acceptance_criteria or [],
            constraints=routing_context.constraints or [],
            agent_config=agent_config,
            namespace_context=inferred_namespace,
            skill_id=signal.skill_id,
            skill_ids=routing_context.skill_ids,
            workflow_mode=routing_context.workflow_mode or "single",
            macro_goal=routing_context.macro_goal,
            parameters=TicketParameters(**parameters) if parameters else None,
        )
        blackboard.ticket = execution_ticket

        # 3. Handle Blackboard/Loop Detection
        visited_nodes = list(blackboard.visited_nodes or [])
        if target not in visited_nodes:
            visited_nodes = visited_nodes + [target]
        blackboard.visited_nodes = visited_nodes

        return StateUpdate(
            next_node=target,
            blackboard=blackboard,
        )

    @staticmethod
    async def _handle_spawn_subtasks(state: AgentState, signal: SpawnSubtasksSignal, config: RunnableConfig) -> StateUpdate:
        spawn_plan = signal.plan
        logger.info(f"[Dispatcher] 🚀 Spawning {len(spawn_plan.subtasks or [])} parallel subtasks")

        blackboard = BlackboardState.model_validate(state.blackboard) if state.blackboard else None
        if not blackboard:
            blackboard = BlackboardState()
        blackboard.spawn_plan = spawn_plan

        if getattr(spawn_plan, "requires_aggregation", False):
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

    @staticmethod
    async def _handle_terminate(state: AgentState, signal: TerminateSignal, config: RunnableConfig) -> StateUpdate:
        logger.info(f"[Dispatcher] 🏁 Natural Termination Signal received. Outcome: {signal.outcome}")

        blackboard = BlackboardState.model_validate(state.blackboard) if state.blackboard else None
        if not blackboard:
            blackboard = BlackboardState()
        blackboard.metadata = (blackboard.metadata or BlackboardMetadata()).model_copy(
            update={"shadow_audit": True, "termination_outcome": signal.outcome}
        )

        return StateUpdate(
            next_node=RoutingTarget.FINISH,
            blackboard=blackboard
        )
