from abc import ABC
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.engine.state.blackboard import SpawnPlan


class AgentSignal(BaseModel, ABC):
    """Base class for all Agent-driven control signals."""
    reason: str = ""


class RouteToSignal(AgentSignal):
    """Signal to transition to another Graph Node."""
    target: str = "finish"
    context: Dict[str, Any] = Field(default_factory=dict)
    authorized_tools: Optional[List[str]] = None
    skill_id: Optional[int] = None


class SpawnSubtasksSignal(AgentSignal):
    """Signal to spawn parallel sub-agents."""
    plan: SpawnPlan = Field(default_factory=SpawnPlan)


class TerminateSignal(AgentSignal):
    """Signal to end the session naturally."""
    summary: str = ""
    outcome: str = "SUCCESS"
