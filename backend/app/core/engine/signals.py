from abc import ABC
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class AgentSignal(ABC):
    """Base class for all Agent-driven control signals."""
    reason: str = ""


@dataclass
class RouteToSignal(AgentSignal):
    """Signal to transition to another Graph Node."""
    target: str = "finish"
    context: dict[str, Any] = field(default_factory=dict)
    authorized_tools: Optional[list[str]] = None


@dataclass
class SpawnSubtasksSignal(AgentSignal):
    """Signal to spawn parallel sub-agents."""
    plan: dict[str, Any] = field(default_factory=dict)


@dataclass
class TerminateSignal(AgentSignal):
    """Signal to end the session naturally."""
    summary: str = ""
    outcome: str = "SUCCESS"
