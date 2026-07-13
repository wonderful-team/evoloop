"""Signal schemas — re-exports from signals module + TerminateSignal."""

from app.core.engine.signals.signals import (
    AgentSignal,
    RouteToSignal,
    RoutingContext,
    SpawnSubtasksSignal,
)


class TerminateSignal(AgentSignal):
    """Signal to terminate execution and route to finish."""
    summary: str = ""

    def type_name(self) -> str:
        return "TerminateSignal"


__all__ = [
    "AgentSignal",
    "RouteToSignal",
    "RoutingContext",
    "SpawnSubtasksSignal",
    "TerminateSignal",
]
