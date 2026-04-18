"""
Signals Package - Registry-based control flow management for EvoLoop Agents.
"""

from .dispatcher import SignalDispatcher
from .manager import signal_manager
from .schema import (
    AgentSignal,
    RouteToSignal,
    RoutingContext,
    SpawnSubtasksSignal,
    TerminateSignal,
)

__all__ = [
    "AgentSignal",
    "RouteToSignal",
    "RoutingContext",
    "SpawnSubtasksSignal",
    "TerminateSignal",
    "SignalDispatcher",
    "signal_manager",
]
