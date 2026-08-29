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
