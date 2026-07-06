"""API schemas for agent routes."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse
from app.constants import DEFAULT_PROJECT_ID
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest


class ChatRequest(ScopedRequest):
    thread_id: str | None = None
    message: str
    project_id: int | None = DEFAULT_PROJECT_ID
    model: str | None = None
    command_id: int | None = None
    checkpoint_id: str | None = None
    message_id: str | None = None
    references: list[dict[str, Any]] | None = None
    skill_ids: list[int] | None = None
    revert_files: bool = True
    scenario: str | None = None


class WebhookRequest(ScopedRequest):
    source: str
    event_type: str
    payload: "WebhookPayload"
    thread_id: str | None = None


class ResumeRequest(ScopedRequest):
    thread_id: str
    user_input: str | None = None
    command_id: int | None = None
    model: str | None = None


class CancelHITLRequest(ScopedRequest):
    thread_id: str
    reason: str | None = None
    model: str | None = None


class WebhookPayload(DynamicBaseModel):
    """External webhook payload. Extra fields are allowed per source/event_type."""


class StopChatResponse(BaseAPIResponse):
    """Response for stopping a chat."""
    status: str
    thread_id: str


class ResumeChatResponse(BaseAPIResponse):
    """Response for resuming a chat."""
    status: str
    thread_id: str


class CancelHITLResponse(BaseAPIResponse):
    """Response for cancelling a HITL request."""
    status: str
    thread_id: str
    request_id: str | None


class WebhookResponse(BaseAPIResponse):
    """Response for webhook endpoint."""
    status: str
    thread_id: str
