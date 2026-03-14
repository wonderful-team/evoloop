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


# --- Human Request Events (HITL + UI Actions) ---
class HumanRequestEvent(EventBase):
    type: Literal["human_request"] = "human_request"
    action: Literal["create", "update", "clear"] = "create"
    data: dict[str, Any]
    # data 结构:
    # {
    #   "type": "text_input" | "project_switch" | "confirm" | "file_select",
    #   "prompt": str,
    #   "allow_cancel": bool,
    #   "payload": {...}  # type-specific data
    # }


# Union type for easy parsing if needed
StreamEvent = (
    StepEvent
    | ArtifactEvent
    | AgentStateEvent
    | TokenEvent
    | StatusEvent
    | MessageEvent
    | HumanRequestEvent
)
