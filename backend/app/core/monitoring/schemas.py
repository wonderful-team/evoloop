"""Schemas for monitoring module."""

from pydantic import Field

from app.core.hitl.types import HumanRequestType
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentActivityState(DynamicBaseModel):
    mode: str
    task_name: str
    task_status: str
    details: dict | None = None
    active_skills: list[dict] | None = None


class HumanRequestData(DynamicBaseModel):
    type: str
    prompt: str
    allow_cancel: bool = True
    payload: dict = Field(default_factory=dict)


class SystemLogPayload(DynamicBaseModel):
    type: str
    data: dict
    timestamp: float


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
