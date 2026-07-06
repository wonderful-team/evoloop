"""Background agent input models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BackgroundAgentInputs(BaseModel):
    """Structured inputs for background agent execution."""

    model_config = ConfigDict(extra="allow")

    messages: list[dict] = Field(default_factory=list)
    project_id: int | None = None
    model: str | None = None
    goal: str = ""
    command_id: str | int | None = None
    checkpoint_id: str | None = None
    is_retry: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    iteration_count: int = 0
    hitl_resume_response: str | None = None
    is_hitl_cancel: bool = False
    session_goal: str | None = None
    working_directory: str | None = None
