import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate

logger = logging.getLogger(__name__)


class SignalDispatcher:
    """
    Centralized dispatcher for AgentSignals (v5.0).
    Uses SignalManager to find and execute handlers.
    Internalized within the signals package.
    """

    @staticmethod
    async def dispatch(state: AgentState, signal: Any, config: RunnableConfig) -> StateUpdate:
        """
        Dispatches the signal using registered handlers and returns the StateUpdate.
        """
        from .manager import signal_manager
        from .schema import AgentSignal
        from app.core.engine.state import ensure_state
        
        # Ensure state is hydrated (safety for dict-based runs)
        state = ensure_state(state)

        if not isinstance(signal, AgentSignal):
            logger.warning(f"[Dispatcher] Unknown signal type received: {type(signal)}")
            return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

        return await signal_manager.dispatch(state, signal, config)
