"""Signal dispatcher — thin wrapper around SignalManager for backwards compat."""

from typing import Any

from app.core.engine.signals.schemas import TerminateSignal
from app.core.engine.signals.signals import (
    AgentSignal,
    StateUpdate,
    signal_manager,
)


class SignalDispatcher:
    """Legacy dispatcher interface wrapping SignalManager singleton."""

    @staticmethod
    async def dispatch(state: Any, signal: AgentSignal | None, config: dict) -> StateUpdate | None:
        if signal is None:
            return None
        if isinstance(signal, TerminateSignal):
            return StateUpdate(next_node="finish")
        return await signal_manager.dispatch(state, signal, config)


__all__ = ["SignalDispatcher"]
