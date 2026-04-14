"""Learning schemas - skills and parameters."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.responses import BaseAPIResponse, ListResponse


class SkillParameter(BaseModel):
    """Shared parameter definition for learned skills."""

    name: str
    type: str = "string"
    description: str = ""
    default: Any | None = None
    required: bool = False


class SkillExecutionParams(DynamicBaseModel):
    """Parameters for skill execution. Extra fields are allowed per skill type."""


class SkillDTO(BaseModel):
    id: int
    name: str
    description: str
    namespace: str | None = None
    trigger_patterns: list[str]
    parameters: list[SkillParameter]
    tools_used: list[str]
    success_count: int
    failure_count: int
    is_active: bool
    status: str
    execution_mode: str = "agentic"
    macro_script: str | None = None  # YAML format
    validation_report: dict[str, Any] | None = None
    instructions: str | None = None
    created_at: datetime
    updated_at: datetime


class SkillDetailResponse(SkillDTO):
    preconditions: list[dict[str, Any]] = []
    source_thread_id: str | None = None
    source_session_id: str | None = None
    resource_path: str | None = None


class SkillResponse(BaseAPIResponse):
    id: int
    name: str
    description: str
    trigger_patterns: list[str]
    tools_used: list[str]
    success_count: int
    failure_count: int
    is_active: bool
