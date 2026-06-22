from abc import ABC

from pydantic import BaseModel, Field, model_validator

from app.core.engine.state.sub_schemas import SpawnPlan
from app.core.engine.state.config import AgentRuntimeConfig
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentSignal(BaseModel, ABC):
    """Base class for all Agent-driven control signals."""
    reason: str = ""


class RoutingContext(DynamicBaseModel):
    """Structured context for RouteToSignal, containing ticket construction parameters."""
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


class RouteToSignal(AgentSignal):
    """Signal to transition to another Graph Node."""
    target: str = "finish"
    context: RoutingContext = Field(default_factory=RoutingContext)
    skill_ids: list[int] | None = None
    session_goal: str | None = None

    @model_validator(mode="after")
    def _normalize_skills(self):
        if self.skill_ids and not self.context.skill_ids:
            self.context.skill_ids = self.skill_ids
        return self


class SpawnSubtasksSignal(AgentSignal):
    """Signal to spawn parallel sub-agents."""
    plan: SpawnPlan = Field(default_factory=SpawnPlan)


class TerminateSignal(AgentSignal):
    """Signal to end the session naturally."""
    summary: str = ""
    outcome: str = "SUCCESS"
