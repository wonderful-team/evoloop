import logging
from typing import Any, Callable, Type, TypeVar, Optional

from langchain_core.runnables import RunnableConfig

from app.core.engine.signals.base import SignalHandler
from app.core.engine.signals.schemas import AgentSignal
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.message.schemas import ToolCall

logger = logging.getLogger(__name__)

S = TypeVar("S", bound=AgentSignal)


class SignalManager:
    """
    Registry and Manager for AgentSignals.
    Decouples tool calls from signal creation and signal types from handlers.
    """

    def __init__(self):
        # tool_name -> (signal_class, factory_fn)
        self._interceptors: dict[str, tuple[Type[AgentSignal], Callable[[dict], AgentSignal]]] = {}
        # signal_class -> handler_instance
        self._handlers: dict[Type[AgentSignal], SignalHandler] = {}

    def register_interceptor(
        self,
        tool_name: str,
        signal_class: Type[AgentSignal],
        factory_fn: Callable[[dict], AgentSignal],
    ):
        """Register a tool to be intercepted and converted into a signal."""
        self._interceptors[tool_name] = (signal_class, factory_fn)
        logger.debug(f"Registered signal interceptor: {tool_name} -> {signal_class.__name__}")

    def register_handler(self, signal_class: Type[AgentSignal], handler: SignalHandler):
        """Register a handler for a specific signal type."""
        self._handlers[signal_class] = handler
        logger.debug(f"Registered signal handler: {signal_class.__name__} -> {handler.__class__.__name__}")

    async def intercept(self, tool_call: ToolCall) -> Optional[AgentSignal]:
        """
        Check if a tool call should be intercepted and converted to a signal.
        (Pre-execution interception)
        """
        if tool_call.name in self._interceptors:
            signal_class, factory_fn = self._interceptors[tool_call.name]
            try:
                signal = factory_fn(tool_call.args)
                logger.info(f"[SignalManager] ⚡ Pre-intercepted tool '{tool_call.name}' -> {signal_class.__name__}")
                return signal
            except Exception as e:
                logger.error(f"Failed to create signal from tool '{tool_call.name}': {e}")
                raise
        return None

    def detect_post_execution_signal(self, tool_name: str, result: Any) -> Optional[AgentSignal]:
        """
        Check if a tool result contains a signal.
        (Post-execution detection)
        """
        # Logic for decompose_task
        if tool_name == "decompose_task" and getattr(result, "spawn_plan", None):
            from .schemas import SpawnSubtasksSignal
            return SpawnSubtasksSignal(plan=result.spawn_plan)
        
        # Generic protocol: result has _signal attribute
        if isinstance(getattr(result, "_signal", None), AgentSignal):
            return result._signal
            
        return None

    async def dispatch(self, state: AgentState, signal: AgentSignal, config: RunnableConfig) -> StateUpdate:
        """
        Dispatch a signal to its registered handler.
        """
        handler = self._handlers.get(type(signal))
        if handler:
            return await handler.handle(state, signal, config)
        
        logger.warning(f"No handler registered for signal type: {type(signal).__name__}")
        # Fallback to supervisor or generic finish if no handler found
        from app.core.engine.routers import RoutingTarget
        return StateUpdate(next_node=RoutingTarget.SUPERVISOR)


# Global Singleton
signal_manager = SignalManager()


def bootstrap_signals():
    """Register core signals and their handlers."""
    from .schemas import RouteToSignal, SpawnSubtasksSignal, TerminateSignal
    from app.core.engine.signals.handlers.routing import RouteToHandler, create_route_to_signal
    from app.core.engine.signals.handlers.task import SpawnSubtasksHandler, TerminateHandler

    # 1. Routing
    signal_manager.register_interceptor("route_to", RouteToSignal, create_route_to_signal)
    signal_manager.register_handler(RouteToSignal, RouteToHandler())

    # 2. Parallel Task Spawning
    signal_manager.register_handler(SpawnSubtasksSignal, SpawnSubtasksHandler())

    # 3. Termination
    signal_manager.register_handler(TerminateSignal, TerminateHandler())


# Auto-initialize on import
bootstrap_signals()
