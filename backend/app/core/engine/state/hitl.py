"""Human-in-the-Loop state models."""
from typing import List, Optional

from pydantic import Field
from app.infrastructure.pydantic_base import DynamicBaseModel


class MessagePayload(DynamicBaseModel):
    pass


class HITLContext(DynamicBaseModel):
    prompt: Optional[str] = None
    options: Optional[List[str]] = None
    default_value: Optional[str] = None
    allow_cancel: bool = True
    payload: MessagePayload = Field(default_factory=MessagePayload)


class HITLState(DynamicBaseModel):
    request_id: str
    request_type: str
    resume_node: str
    context: HITLContext = Field(default_factory=HITLContext)
    created_at: Optional[str] = None
