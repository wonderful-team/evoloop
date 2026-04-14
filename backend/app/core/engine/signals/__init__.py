"""
Signals Package - Registry-based control flow management for EvoLoop Agents.
"""

from .schema import (
    AgentSignal,
    RouteToSignal,
    RoutingContext,
    SpawnSubtasksSignal,
    TerminateSignal,
)
from .dispatcher import SignalDispatcher
from .manager import signal_manager

__all__ = [
    "AgentSignal",
    "RouteToSignal",
    "RoutingContext",
    "SpawnSubtasksSignal",
    "TerminateSignal",
    "SignalDispatcher",
    "signal_manager",
]
