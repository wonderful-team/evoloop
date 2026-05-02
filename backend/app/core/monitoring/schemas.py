"""Schemas for monitoring module."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class HumanRequestType(str, Enum):
    """Types of human requests that backend can make."""

    # Traditional text input
    TEXT_INPUT = "text_input"
    """Request text input from user (traditional HITL)."""

    # Project-related
    PROJECT_SWITCH = "project_switch"
    """Request user to switch to a specific project or select from list."""

    # Confirmation
    CONFIRM = "confirm"
    """Request yes/no confirmation from user."""

    # Approval
    APPROVAL = "approval"
    """Request explicit approval for impactful actions."""

    # File selection
    FILE_SELECT = "file_select"
    """Request user to select one or more files."""


class AgentActivityState(DynamicBaseModel):
    mode: str
    task_name: str
    task_status: str
    details: dict | None = None

class HumanRequestData(DynamicBaseModel):
    type: str
    prompt: str
    allow_cancel: bool = True
    payload: dict = Field(default_factory=dict)

class SystemLogPayload(DynamicBaseModel):
    type: str
    data: dict
    timestamp: float

class PromptStats(BaseModel):
    """Metrics for the input prompt."""
    system_len: int = 0
    history_len: int = 0
    total_len: int = 0

class UsageMetadata(BaseModel):
    """Token usage metrics from the LLM provider."""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

class ResponseStats(BaseModel):
    """Metrics for the LLM response."""
    content_len: int = 0
    is_tool_call: bool = False
    tool_names: list[str] = Field(default_factory=list)

class InferenceEvent(DynamicBaseModel):
    """A complete record of a single inference call."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    node_name: str
    turn_id: int
    latency_ms: float
    prompt: PromptStats
    usage: UsageMetadata
    response: ResponseStats
    metadata: dict[str, Any] = Field(default_factory=dict)

class TextInputRequest(DynamicBaseModel):
    """Human request for text input."""
    type: HumanRequestType
    prompt: str
    placeholder: str = "Enter your response..."
    multiline: bool = False
    allow_cancel: bool = True

class ProjectSwitchPayload(DynamicBaseModel):
    """Payload for project switch request."""
    allow_global: bool = False
    suggested_project_id: int | None = None
    show_project_list: bool = True
    temporary: bool = True

class ProjectSwitchRequest(DynamicBaseModel):
    """Human request for project switch."""
    type: HumanRequestType
    prompt: str
    allow_cancel: bool = True
    payload: ProjectSwitchPayload

class ConfirmPayload(DynamicBaseModel):
    """Payload for confirmation request."""
    confirm_text: str = "Confirm"
    cancel_text: str = "Cancel"

class ConfirmRequest(DynamicBaseModel):
    """Human request for confirmation."""
    type: HumanRequestType
    prompt: str
    title: str = "Confirmation Required"
    allow_cancel: bool = True
    payload: ConfirmPayload

class FileSelectPayload(DynamicBaseModel):
    """Payload for file selection request."""
    multiple: bool = False
    file_types: list[str] = []

class FileSelectRequest(DynamicBaseModel):
    """Human request for file selection."""
    type: HumanRequestType
    prompt: str
    allow_cancel: bool = True
    payload: FileSelectPayload
