import time
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class EventBase(BaseModel):
    timestamp: float = Field(default_factory=time.time)

# --- Task Events ---
class TaskEvent(EventBase):
    type: Literal["task"] = "task"
    action: Literal["create", "update"]
    id: int
    data: dict[str, Any]  # The delta or full object

# --- Artifact Events ---
class ArtifactEvent(EventBase):
    type: Literal["artifact"] = "artifact"
    action: Literal["create", "update"]
    name: str = "" # Usually keyed by name or ID, let's assume we pass enough info
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

# Union type for easy parsing if needed
StreamEvent = Union[TaskEvent, ArtifactEvent, AgentStateEvent, TokenEvent, StatusEvent]
