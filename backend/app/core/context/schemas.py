"""Schemas for context module."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from pydantic import BaseModel
from pydantic import Field
from typing import Any
from typing import Any, Optional
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import ExecutionTicket

class DynamicContextLayer(DynamicBaseModel):
    """Dynamic context that must always be fresh."""
    blackboard: BlackboardState | None = None
    execution_ticket: ExecutionTicket | None = None
    messages: list = Field(default_factory=list)
    iteration_count: int = 0

class ContextMetadata(DynamicBaseModel):
    """Dynamic metadata attached to an EvoContext."""
    has_android: bool | None = None
    has_macos: bool | None = None
    user_preferences: Any | None = None
    project_concepts: Any | None = None
    active_skills: Any | None = None
    environment_telemetry: Any | None = None
    blackboard: Any | None = None
    execution_ticket: Any | None = None
    iteration_count: int | None = None
    active_plan_context: str | None = None
    prompt: str | None = None
