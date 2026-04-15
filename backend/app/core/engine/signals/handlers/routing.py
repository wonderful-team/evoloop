import logging
from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from ..schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    TicketParameters,
)
from app.core.engine.signals.base import SignalHandler

logger = logging.getLogger(__name__)


class RouteToHandler(SignalHandler[RouteToSignal]):
    """Handler for RouteToSignal."""

    async def handle(
        self, state: AgentState, signal: RouteToSignal, config: RunnableConfig
    ) -> StateUpdate:
        target = signal.target
        reason = signal.reason
        routing_context = signal.context
        authorized_tools = signal.authorized_tools

        logger.info(f"[SignalHandler] ✅ Intercepted route_to -> {target} | Reason: {reason}")

        # 1. Update Blackboard
        blackboard = state.blackboard # Already guaranteed to be BlackboardState
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


def create_route_to_signal(args: dict) -> RouteToSignal:
    """Factory for RouteToSignal from tool arguments."""
    import json
    context_data = args.get("context", {})
    if isinstance(context_data, str):
        try:
            context_data = json.loads(context_data)
        except Exception:
            context_data = {}
            
    return RouteToSignal(
        target=args.get("target", RoutingTarget.FINISH),
        reason=args.get("reason", ""),
        context=RoutingContext.model_validate(context_data) if context_data else RoutingContext(),
        authorized_tools=args.get("authorized_tools"),
        skill_id=args.get("skill_id"),
    )
