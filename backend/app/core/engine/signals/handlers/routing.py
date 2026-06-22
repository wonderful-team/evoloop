import logging

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.base import SignalHandler
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    TicketParameters,
)
from ..schemas import RouteToSignal, RoutingContext

logger = logging.getLogger(__name__)


class RouteToHandler(SignalHandler[RouteToSignal]):
    """Handler for RouteToSignal."""

    async def handle(
        self, state: AgentState, signal: RouteToSignal, config: RunnableConfig
    ) -> StateUpdate:
        target = signal.target
        reason = signal.reason
        routing_context = signal.context

        logger.info(f"[SignalHandler] ✅ Intercepted route_to -> {target} | Reason: {reason}")

        # 1. Construct Execution Ticket
        inferred_namespace = routing_context.namespace_context

        # Start with preset agent_config (if any), then overlay routing_context
        preset_config = state.ticket.agent_config if state.ticket and state.ticket.agent_config else None
        agent_config = preset_config or AgentRuntimeConfig()
        
        # Overlay routing_context's agent_config fields
        if routing_context.agent_config:
            if routing_context.agent_config.role_name:
                agent_config.role_name = routing_context.agent_config.role_name
            if routing_context.agent_config.system_instructions:
                agent_config.system_instructions = routing_context.agent_config.system_instructions
            if routing_context.agent_config.namespace_context:
                agent_config.namespace_context = routing_context.agent_config.namespace_context
            if routing_context.agent_config.model_override:
                agent_config.model_override = routing_context.agent_config.model_override
        
        if not agent_config.namespace_context:
            agent_config.namespace_context = inferred_namespace
        if not agent_config.role_name:
            agent_config.role_name = str(target).replace("_", " ").title()

        parameters_fields = set(TicketParameters.model_fields.keys())
        parameters = {k: v for k, v in routing_context.model_dump().items() if k in parameters_fields}


        context_dump = routing_context.model_dump()
        historical_context = context_dump.get("historical_context")
        referenced_tech = context_dump.get("referenced_tech")

        normalized_skill_ids = routing_context.skill_ids or signal.skill_ids

        execution_ticket = ExecutionTicket(
            ticket_type=routing_context.ticket_type or "task",
            priority=routing_context.priority or "normal",
            focus_paths=routing_context.focus_paths or [],
            topic=routing_context.topic or routing_context.query or reason,
            acceptance_criteria=routing_context.acceptance_criteria or [],
            constraints=routing_context.constraints or [],
            agent_config=agent_config,
            namespace_context=inferred_namespace,
            skill_ids=normalized_skill_ids,  # type: ignore[arg-type]
            workflow_mode=routing_context.workflow_mode or "single",
            macro_goal=routing_context.macro_goal,
            parameters=TicketParameters(**parameters) if parameters else None,
            historical_context=historical_context,
            referenced_tech=referenced_tech,
        )
        target_name = target.value if hasattr(target, 'value') else str(target)
        logger.info(
            f"[Routing] ExecutionTicket dispatched to {target_name} | "
            f"topic='{execution_ticket.topic}' | "
            f"skill_ids={execution_ticket.skill_ids} | "
            f"tools={agent_config.tools if agent_config else []} | "
            f"acceptance={execution_ticket.acceptance_criteria}"
        )

        # 2. Handle Visited Nodes/Loop Detection
        visited_nodes = list(state.visited_nodes or [])
        if target not in visited_nodes:
            visited_nodes = visited_nodes + [target]

        # 3. Update session goal in database and publish event if provided
        session_goal = signal.session_goal
        if session_goal:
            from app.core.engine.message.goal_distiller import GoalDistiller
            session_goal = GoalDistiller.from_explicit(session_goal) or ""
            if session_goal:
                if not state.thread_id:
                    logger.warning(
                        "[Routing] Skipping session goal update: state.thread_id is None. "
                        f"goal='{session_goal[:80]}'"
                    )
                else:
                    try:
                        from app.core.monitoring.activity import activity_monitor
                        await activity_monitor.update_goal(state.thread_id, session_goal)
                    except Exception as e:
                        logger.warning(f"Failed to update session goal in RouteToHandler: {e}")

        return StateUpdate(
            next_node=target,
            route_reason=reason,
            ticket=execution_ticket,
            visited_nodes=visited_nodes,
            session_goal=session_goal if session_goal is not None else state.session_goal,
        )


def create_route_to_signal(args: dict) -> RouteToSignal:
    """Factory for RouteToSignal from tool arguments."""
    import json
    context_data = args.get("context", {})
    if isinstance(context_data, str):
        try:
            context_data = json.loads(context_data)
        except (json.JSONDecodeError, TypeError, ValueError):
            context_data = {}

    if isinstance(context_data, dict):
        for field in ["skill_ids", "workflow_mode", "historical_context", "referenced_tech"]:
            if field in args and field not in context_data:
                context_data[field] = args[field]

    raw_skill_ids = args.get("skill_ids") or (context_data.get("skill_ids") if isinstance(context_data, dict) else None)

    return RouteToSignal(
        target=args.get("target", RoutingTarget.FINISH),
        reason=args.get("reason", ""),
        context=RoutingContext.model_validate(context_data) if context_data else RoutingContext(),
        skill_ids=raw_skill_ids,
        session_goal=args.get("session_goal"),
    )
