"""Human-in-the-Loop state models."""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class MessagePayload(DynamicBaseModel):
    pass


class HITLContext(DynamicBaseModel):
    prompt: str | None = None
    options: list[str] | None = None
    default_value: str | None = None
    allow_cancel: bool = True
    payload: MessagePayload = Field(default_factory=MessagePayload)


class HITLState(DynamicBaseModel):
    request_id: str
    request_type: str
    resume_node: str
    context: HITLContext = Field(default_factory=HITLContext)
    created_at: str | None = None
