"""
SignalRegistry - Plugin-based signal interception for Agent control flows.

Replaces hardcoded signal logic in AgentEngine with a configurable registry.
All control signals (route_to, decompose_task, pause_and_wait, etc.) are
registered as interceptors, making the engine truly generic.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Callable

from langchain_core.runnables import RunnableConfig

from app.core.engine.signals import AgentSignal, RouteToSignal, SpawnSubtasksSignal
from app.core.engine.state.blackboard import SpawnPlan

logger = logging.getLogger(__name__)


class SignalEmitter:
    """
    Unified emitter for agent-internal signals.

    Ensures intercepted tools (like route_to) trigger standard on_tool_start/end
    callbacks so observability systems see them as first-class events.
    """

    @staticmethod
    async def emit_tool_start(tool_name: str, tool_input: dict, run_id: str, config: RunnableConfig):
        """Emit on_tool_start to all compatible callbacks in config."""
        callbacks = config.get("callbacks", []) if config else []
        callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
        for cb in callback_list:
            if hasattr(cb, "on_tool_start"):
                await cb.on_tool_start(
                    serialized={"name": tool_name},
                    input_str=json.dumps(tool_input, ensure_ascii=False),
                    run_id=run_id,
                )

    @staticmethod
    async def emit_tool_end(tool_name: str, output: str, run_id: str, config: RunnableConfig):
        """Emit on_tool_end to all compatible callbacks in config."""
        callbacks = config.get("callbacks", []) if config else []
        callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
        for cb in callback_list:
            if hasattr(cb, "on_tool_end"):
                await cb.on_tool_end(output=output, run_id=run_id)


class ToolCallInterceptor(ABC):
    """Base class for tool-call interceptors that convert tool calls into AgentSignals."""

    @abstractmethod
    async def intercept(self, tool_call: dict, config: RunnableConfig) -> AgentSignal | None:
        """
        Intercept a tool call and optionally return an AgentSignal.

        If a signal is returned, the engine aborts the current turn and
        dispatches the signal.
        """
        ...


class RouteToInterceptor(ToolCallInterceptor):
    """Intercepts route_to tool calls and converts them to RouteToSignal."""

    async def intercept(self, tool_call: dict, config: RunnableConfig) -> RouteToSignal | None:
        tc_id = tool_call["id"]
        args = tool_call.get("args", {})

        await SignalEmitter.emit_tool_start("route_to", args, tc_id, config)

        target = args.get("target", "finish")
        reason = args.get("reason", "")
        context = args.get("context", {})
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except Exception:
                context = {}

        authorized_tools = args.get("authorized_tools")

        logger.info(f"[SignalRegistry] Intent: -> {target} ({reason})")

        skill_ids = args.get("skill_ids")
        if not skill_ids and args.get("skill_id"):
            skill_ids = [args.get("skill_id")]

        session_goal = args.get("session_goal")

        signal = RouteToSignal(
            target=target,
            reason=reason,
            context=context,
            authorized_tools=authorized_tools,
            skill_ids=skill_ids,
            session_goal=session_goal,
        )

        output_msg = f"Routing to {target}"
        await SignalEmitter.emit_tool_end("route_to", output_msg, tc_id, config)
        return signal


class DecomposeTaskInterceptor(ToolCallInterceptor):
    """Intercepts decompose_task tool calls and converts them to SpawnSubtasksSignal."""

    async def intercept(self, tool_call: dict, config: RunnableConfig) -> SpawnSubtasksSignal | None:
        tc_id = tool_call["id"]
        args = tool_call.get("args", {})

        await SignalEmitter.emit_tool_start("decompose_task", args, tc_id, config)

        # Execute the actual decompose_task tool to get the plan
        from app.core.tools.executor import ToolExecutor
        executor = ToolExecutor()

        # Need to locate the tool instance
        # Since we are in the interceptor, the tool_map is not directly available.
        # The decompose_task tool is a global tool; we can look it up.
        from app.core.tools.registry import get_tool_map
        tool = get_tool_map().get("decompose_task")
        if not tool:
            logger.warning("[SignalRegistry] decompose_task tool not found in registry")
            await SignalEmitter.emit_tool_end("decompose_task", "Tool not found", tc_id, config)
            return None

        result = await executor.execute(tool, args, config=config)

        if isinstance(result, dict) and result.get("_spawn_plan"):
            spawn_plan = SpawnPlan.model_validate(result["_spawn_plan"])
            logger.info(f"[SignalRegistry] Intent: Spawn {len(spawn_plan.subtasks or [])} subtasks")

            await SignalEmitter.emit_tool_end(
                "decompose_task",
                f"Task decomposed into {len(spawn_plan.subtasks or [])} subtasks.",
                tc_id,
                config,
            )
            return SpawnSubtasksSignal(plan=spawn_plan)

        await SignalEmitter.emit_tool_end("decompose_task", str(result), tc_id, config)
        return None


class SignalRegistry:
    """
    Registry for tool-call interceptors.

    New interceptors can be added via register() without modifying the engine core.
    """

    def __init__(self):
        self._handlers: dict[str, ToolCallInterceptor] = {}

    def register(self, tool_name: str, interceptor: ToolCallInterceptor) -> None:
        """Register an interceptor for a tool name."""
        self._handlers[tool_name] = interceptor
        logger.info(f"[SignalRegistry] Registered interceptor for '{tool_name}'")

    def get_handler(self, tool_name: str) -> ToolCallInterceptor | None:
        """Get the interceptor for a tool name, if any."""
        return self._handlers.get(tool_name)

    def build_interceptors(self) -> dict[str, Callable]:
        """
        Build a mapping suitable for InferenceEngine.interceptors.

        Returns a dict of tool_name -> async callable(tool_call, config) -> AgentSignal|None
        """
        interceptors = {}
        for tool_name, handler in self._handlers.items():
            interceptors[tool_name] = handler.intercept
        return interceptors


# Default global registry with built-in interceptors
_default_registry: SignalRegistry | None = None


def get_default_registry() -> SignalRegistry:
    """Get or create the default SignalRegistry with built-in interceptors."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SignalRegistry()
        _default_registry.register("route_to", RouteToInterceptor())
        _default_registry.register("decompose_task", DecomposeTaskInterceptor())
    return _default_registry


def set_default_registry(registry: SignalRegistry) -> None:
    """Override the default registry (useful for testing)."""
    global _default_registry
    _default_registry = registry
