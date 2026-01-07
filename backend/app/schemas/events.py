from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field
import time

class EventBase(BaseModel):
    timestamp: float = Field(default_factory=time.time)

# --- Task Events ---
class TaskEvent(EventBase):
    type: Literal["task"] = "task"
    action: Literal["create", "update"]
    id: int
    data: Dict[str, Any]  # The delta or full object

# --- Artifact Events ---
class ArtifactEvent(EventBase):
    type: Literal["artifact"] = "artifact"
    action: Literal["create", "update"]
    name: str = "" # Usually keyed by name or ID, let's assume we pass enough info
    data: Dict[str, Any]

# --- Agent State Events ---
class AgentStateEvent(EventBase):
    type: Literal["state"] = "state"
    action: Literal["update"] = "update"
    data: Dict[str, Any]

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
