"""Agent signal system — schemas, interceptors, handlers, and registry.

Everything in one module: signal types, tool-call interceptors, signal handlers,
and a single SignalManager singleton.

Signals are Pydantic models (need serialization for state.pending_signals).
Interceptors are plain async functions: (tool_call, config) -> AgentSignal | None.
Handlers are plain async functions: (state, signal, config) -> StateUpdate.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.engine.message.native_classes import AIMessage
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    TicketParameters,
)
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.extract import safe_parse_json

logger = logging.getLogger(__name__)


# ───────────────────────── Signal Schemas ─────────────────────────


class AgentSignal(BaseModel):
    """Base class for agent control signals."""

    reason: str = ""

    def type_name(self) -> str:
        return type(self).__name__


class RoutingContext(DynamicBaseModel):
    """Structured context for RouteToSignal."""

    ticket_type: str = "task"
    priority: str = "normal"
    focus_paths: list[str] = Field(default_factory=list)
    topic: str | None = None
    query: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    agent_config: AgentRuntimeConfig | None = None
    namespace_context: str | None = None
    skill_ids: list[int] | None = None
    workflow_mode: str = "single"
    macro_goal: str | None = None
    historical_context: Any | None = None
    referenced_tech: Any | None = None
    dependencies: list[str] | None = None
    verbose_output: bool = True


class RouteToSignal(AgentSignal):
    """Signal to transition to another node."""

    target: str = "finish"
    context: RoutingContext = Field(default_factory=RoutingContext)
    skill_ids: list[int] | None = None
    session_goal: str | None = None

    @model_validator(mode="after")
    def _normalize_skills(self):
        if self.skill_ids and not self.context.skill_ids:
            self.context.skill_ids = self.skill_ids
        return self


# ───────────────────────── Interceptors ─────────────────────────


async def _emit_tool_event(event: str, tool_name: str, input_or_output: Any, run_id: str, config: dict) -> None:
    """Emit on_tool_start/on_tool_end to callbacks in config."""
    callbacks = config.get("callbacks", []) if config else []
    for cb in callbacks:
        fn = getattr(cb, f"on_tool_{event}", None)
        if fn:
            if event == "start":
                await fn(
                    serialized={"name": tool_name},
                    input_str=json.dumps(input_or_output, ensure_ascii=False),
                    run_id=run_id,
                )
            else:
                await fn(output=input_or_output, run_id=run_id)


async def intercept_route_to(tool_call: dict, config: dict) -> RouteToSignal | None:
    """Intercept route_to tool calls → RouteToSignal (tool is NOT executed)."""
    tc_id = tool_call["id"]
    args = tool_call.get("args", {}) or {}
    if isinstance(args, str):
        args = safe_parse_json(args) or {}

    await _emit_tool_event("start", "route_to", args, tc_id, config)

    target = args.get("target", "finish")
    reason = args.get("reason", "")
    context_data = args.get("context", {})
    if isinstance(context_data, str):
        context_data = safe_parse_json(context_data) or {}

    if isinstance(context_data, dict):
        for field in ["skill_ids", "workflow_mode"]:
            if field in args and field not in context_data:
                context_data[field] = args[field]

    if not reason:
        reason = (
            context_data.get("topic")
            or context_data.get("query")
            or f"Proceed with {target}"
        )

    skill_ids = args.get("skill_ids") or (
        context_data.get("skill_ids") if isinstance(context_data, dict) else None
    )

    logger.info(f"[Signals] Intent: -> {target} ({reason})")

    signal = RouteToSignal(
        target=target,
        reason=reason,
        context=RoutingContext.model_validate(context_data) if context_data else RoutingContext(),
        skill_ids=skill_ids,
        session_goal=args.get("session_goal"),
    )

    await _emit_tool_event("end", "route_to", f"Routing to {target}", tc_id, config)
    return signal


async def _resolve_skill_tool_allowlist(skill_ids: list[int | str]) -> list[str]:
    """Union tools_required from the given LearnedSkill IDs.

    Returns an empty list when no skills match or the field is empty, so the
    caller can fall back to the full YAML tool pool.
    """
    if not skill_ids:
        return []
    try:
        from app.core.learning.skills.repository import skill_repository

        skills = await skill_repository.get_by_ids(skill_ids, visible_only=False)
        tools: set[str] = set()
        for skill in skills:
            if skill.tools_used:
                tools.update(skill.tools_used)
        return sorted(tools)
    except Exception as e:
        logger.warning(f"[Signals] Failed to resolve skill tools: {e}", exc_info=True)
        return []


# ───────────────────────── Handlers ─────────────────────────


# Verification-intent keywords used for lineage / anti-loop heuristics.
def _normalize_topic(text: str) -> str:
    """Remove whitespace/punctuation so topic comparisons survive spaces."""
    import re

    return re.sub(r"[\s_\-，,。.?！!？]+", "", text.lower())


def _same_topic(blocked_topic: str, current_topic: str) -> bool:
    """Structural identity check between two topic strings."""
    if not blocked_topic or not current_topic:
        return False
    blocked = _normalize_topic(blocked_topic)
    current = _normalize_topic(current_topic)
    if not blocked or not current:
        return False
    if blocked in current or current in blocked:
        return True
    import re

    blocked_ids = set(re.findall(r"\d{6,}", blocked_topic))
    current_ids = set(re.findall(r"\d{6,}", current_topic))
    return bool(blocked_ids and current_ids and (blocked_ids & current_ids))


def _is_topic_blocked(state: AgentState, routing_context: RoutingContext) -> bool:
    """Return True if the new route topic matches any previously blocked verification topic."""
    shared = state.shared_context or {}
    current = routing_context.topic or routing_context.query or ""
    if not current:
        return False

    # New multi-topic list
    blocked_topics = shared.get("verification_blocked_topics") or []
    if isinstance(blocked_topics, list):
        for blocked in blocked_topics:
            if _same_topic(str(blocked), current):
                return True

    # Backward compatibility with single-topic key
    blocked_topic = shared.get("verification_blocked_topic") or ""
    return _same_topic(str(blocked_topic), current)


async def handle_route_to(state: AgentState, signal: RouteToSignal, _config: dict) -> StateUpdate:
    """Handle RouteToSignal: construct ExecutionTicket and route."""
    target = signal.target
    reason = signal.reason
    routing_context = signal.context

    logger.info(f"[Signals] ✅ route_to -> {target} | {reason}")

    # Structural anti-loop guard: if this exact topic was already proven
    # unverifiable in this thread, do not dispatch another Worker for it.
    shared = state.shared_context or {}
    if (
        target == RoutingTarget.WORKER
        and shared.get("verification_impossible")
        and _is_topic_blocked(state, routing_context)
    ):
        logger.info(
            "[Signals] Blocking repeated route_to for topic already known to be unverifiable."
        )
        final_report = shared.get("verification_block_reason", "The current environment cannot verify macro outcomes.")
        final_msg = AIMessage(
            content=(
                "[SYSTEM FINAL REPORT] The requested action was attempted via macro, "
                "but the environment cannot verify the outcome. "
                f"Reason: {final_report}\n\n"
                "Finishing the task and reporting the current known state to the user."
            )
        )
        return StateUpdate(
            next_node=RoutingTarget.FINISH,
            messages=state.messages + [final_msg],
            route_reason="blocked_repeated_verification",
        )

    inferred_namespace = routing_context.namespace_context

    preset_config = (
        state.ticket.agent_config
        if state.ticket and state.ticket.agent_config
        else None
    )
    agent_config = preset_config or AgentRuntimeConfig()

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

    # Enforce tool allowlist derived from skill requires.tools.
    # Falls back to the full YAML pool when no skill context is present.
    skill_ids = routing_context.skill_ids or signal.skill_ids
    if skill_ids:
        allowed_tools = await _resolve_skill_tool_allowlist(skill_ids)
        if allowed_tools:
            agent_config.tools = sorted(
                set((agent_config.tools or []) + allowed_tools)
            )

    parameters = routing_context.model_dump(
        include={"dependencies", "verbose_output"},
        exclude_none=True,
    )

    historical_context = routing_context.historical_context

    execution_ticket = ExecutionTicket(
        ticket_type=routing_context.ticket_type or "task",
        priority=routing_context.priority or "normal",
        focus_paths=routing_context.focus_paths or [],
        topic=routing_context.topic or routing_context.query or reason,
        acceptance_criteria=routing_context.acceptance_criteria or [],
        constraints=routing_context.constraints or [],
        agent_config=agent_config,
        namespace_context=inferred_namespace,
        skill_ids=routing_context.skill_ids or signal.skill_ids,
        workflow_mode=routing_context.workflow_mode or "single",
        macro_goal=routing_context.macro_goal,
        parameters=TicketParameters(**parameters) if parameters else None,
        historical_context=historical_context,
        referenced_tech=routing_context.referenced_tech,
    )

    visited_nodes = state.visited_nodes or []
    if target not in visited_nodes:
        visited_nodes = visited_nodes + [target]

    session_goal = signal.session_goal
    if session_goal:
        from app.core.engine.message.goal_distiller import GoalDistiller

        session_goal = GoalDistiller.from_explicit(session_goal) or ""
        if session_goal and state.thread_id:
            try:
                from app.core.monitoring.activity import activity_monitor

                await activity_monitor.update_goal(state.thread_id, session_goal)
            except Exception as e:
                logger.warning(f"[Signals] Failed to update session goal: {e}", exc_info=True)

    return StateUpdate(
        next_node=target,
        route_reason=reason,
        ticket=execution_ticket,
        visited_nodes=visited_nodes,
        session_goal=session_goal if session_goal is not None else state.session_goal,
    )


# ───────────────────────── Signal Manager ─────────────────────────


class SignalManager:
    """Registry + dispatcher for agent signals."""

    def __init__(self):
        # tool_name -> async (tool_call, config) -> AgentSignal | None
        self._interceptors: dict[str, Callable] = {}
        # signal_class -> async (state, signal, config) -> StateUpdate
        self._handlers: dict[type[AgentSignal], Callable] = {}

    def register_interceptor(self, tool_name: str, fn: Callable) -> None:
        self._interceptors[tool_name] = fn

    def register_handler(self, signal_class: type[AgentSignal], fn: Callable) -> None:
        self._handlers[signal_class] = fn

    def build_interceptors(self) -> dict[str, Callable]:
        return dict(self._interceptors)

    def detect_post_execution_signal(self, tool_name: str, result: Any) -> AgentSignal | None:
        """Check if a tool result carries a signal (post-execution)."""
        if isinstance(getattr(result, "_signal", None), AgentSignal):
            return result._signal
        return None

    async def dispatch(
        self, state: AgentState, signal: AgentSignal, config: dict
    ) -> StateUpdate | None:
        """Dispatch a signal to its registered handler."""
        handler = self._handlers.get(type(signal))
        if handler:
            return await handler(state, signal, config)

        logger.warning(f"[Signals] No handler for {type(signal).__name__}")
        return StateUpdate(next_node=RoutingTarget.SUPERVISOR)


signal_manager = SignalManager()


# ───────────────────────── Bootstrap ─────────────────────────

# Register interceptors
signal_manager.register_interceptor("route_to", intercept_route_to)

# Register handlers
signal_manager.register_handler(RouteToSignal, handle_route_to)
