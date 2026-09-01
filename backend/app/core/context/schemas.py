"""Schemas for context module."""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ContextMetadata(DynamicBaseModel):
    """Dynamic metadata attached to an EvoContext."""

    source: str | None = None
    has_android: bool | None = None
    has_macos: bool | None = None
    user_preferences: Any | None = None
    project_concepts: Any | None = None
    active_skills: Any | None = None
    active_macros: Any | None = None
    operation_map: str | None = None
    shared_context: dict[str, Any] = Field(default_factory=dict)
    tool_memory: dict | None = None
    iteration_count: int | None = None
    active_plan_context: str | None = None
    prompt: str | None = None
    blackboard: Any | None = None

    # Memory pipeline — populated by AgentContextHydrator
    # Corresponds to Jinja2 template vars: memory.core_raw / memory.episodic_raw
    core_memory_raw: str | None = None
    episodic_memory_raw: str | None = None

    # L0 intent hint passed from entry points to context hydrator
    intent_hint: Any | None = None
