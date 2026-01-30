import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventBase(BaseModel):
    timestamp: float = Field(default_factory=time.time)


# --- Step Events (formerly Task Events) ---
class StepEvent(EventBase):
    type: Literal["step"] = "step"
    action: Literal["create", "update"]
    id: int
    data: dict[str, Any]  # The delta or full object


# --- Artifact Events ---
class ArtifactEvent(EventBase):
    type: Literal["artifact"] = "artifact"
    action: Literal["create", "update"]
    name: str = ""  # Usually keyed by name or ID, let's assume we pass enough info
    data: dict[str, Any]


# --- Agent State Events ---
class AgentStateEvent(EventBase):
    type: Literal["state"] = "state"
    action: Literal["update"] = "update"
    data: dict[str, Any]


# --- Token Events (for consistency, though usually raw) ---
class TokenEvent(EventBase):
    type: Literal["token"] = "token"
    content: str


# --- Error/Status Events ---
class StatusEvent(EventBase):
    type: Literal["status"] = "status"
    status: str


# --- Message Events ---
class MessageEvent(EventBase):
    type: Literal["message"] = "message"
    action: Literal["create"] = "create"
    data: dict[str, Any]  # Serialized Message model


# Union type for easy parsing if needed
StreamEvent = (
    StepEvent | ArtifactEvent | AgentStateEvent | TokenEvent | StatusEvent | MessageEvent
)
