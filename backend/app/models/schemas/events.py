import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class EventBase(DynamicBaseModel):
    timestamp: float = Field(default_factory=time.time)


# --- Step Events ---
class StepEvent(EventBase):
    type: Literal["step"] = "step"
    action: Literal["create", "update"]
    id: int
    data: Dict[str, Any]  # Delta or full object


# --- Artifact Events ---
class ArtifactPayload(DynamicBaseModel):
    name: str
    artifact_type: str  # "code", "design", "log"
    path: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArtifactEvent(EventBase):
    type: Literal["artifact"] = "artifact"
    action: Literal["create", "update"]
    name: str = ""
    data: Union[ArtifactPayload, Dict[str, Any]]


# --- Agent State Events ---
class AgentStateEvent(EventBase):
    type: Literal["state"] = "state"
    action: Literal["update"] = "update"
    data: Dict[str, Any]


# --- Token Events ---
class TokenEvent(EventBase):
    type: Literal["token"] = "token"
    content: str


# --- Error/Status Events ---
class StatusEvent(EventBase):
    type: Literal["status"] = "status"
    status: str
    message: Optional[str] = None


# --- Message Events ---
class MessageEvent(EventBase):
    type: Literal["message"] = "message"
    action: Literal["create"] = "create"
    data: Dict[str, Any]  # Serialized Message model


# --- Human Request Events ---
class HumanRequestPayload(DynamicBaseModel):
    type: Literal["text_input", "project_switch", "confirm", "file_select", "approval"]
    prompt: str
    allow_cancel: bool = True
    payload: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[List[str]] = None


class HumanRequestEvent(EventBase):
    type: Literal["human_request"] = "human_request"
    action: Literal["create", "update", "clear"] = "create"
    data: Union[HumanRequestPayload, Dict[str, Any]]


# --- Quota Exhausted Event ---
class QuotaExhaustedEvent(EventBase):
    type: Literal["quota_exhausted"] = "quota_exhausted"
    title: str = "Quota Exhausted"
    message: str = "Your LLM quota has been exhausted."
    hint: str = "Please contact the administrator to add more quota."
    action_text: str = "Check Quota"


# Union type for easy parsing
StreamEvent = Union[
    StepEvent,
    ArtifactEvent,
    AgentStateEvent,
    TokenEvent,
    StatusEvent,
    MessageEvent,
    HumanRequestEvent,
    QuotaExhaustedEvent
]
