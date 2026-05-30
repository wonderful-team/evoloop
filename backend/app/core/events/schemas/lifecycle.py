"""
Core Event Schemas - Lifecycle
==============================

Event schemas for system-wide lifecycle and status events.
"""
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage
from pydantic import Field, BaseModel, model_validator

from app.core.events.base import BaseEvent
from app.core.events.registry import SystemEventType


class SessionCompletedData(BaseModel):
    """Payload data for SESSION_COMPLETED event."""
    thread_id: str
    run_id: str | None = None
    project_id: int | None = None
    user_id: Optional[str] = None
    messages: List[BaseMessage] = Field(default_factory=list)
    blackboard_dict: dict = Field(default_factory=dict, description="Serialized blackboard state")
    summary: Optional[str] = None
    outcome: Optional[str] = None
    audit_tier: Optional[str] = None
    duration_ms: float = 0.0
    # Extra context for learning and domain modules
    model: str | None = None
    original_skill_id: Optional[Any] = None
    ticket_topic: Optional[str] = None
    ticket_reason: Optional[str] = None


class SessionCompletedEvent(BaseEvent):
    """Event published when an agent session reaches a successful conclusion."""
    event_type: str = SystemEventType.SESSION_COMPLETED
    data: SessionCompletedData
    
    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    @model_validator(mode="after")
    def sync_metadata(self) -> "SessionCompletedEvent":
        """Link internal thread_id for routing."""
        if self.data and hasattr(self.data, "thread_id"):
            self.thread_id = self.data.thread_id
        return self

    def to_frontend_payload(self) -> dict:
        """Map to legacy session_completed format."""
        return {
            "type": "session_completed",
            "thread_id": self.thread_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data.model_dump(exclude={"messages", "blackboard_dict"})
        }


class SystemStatusEvent(BaseEvent):
    """Event representing a high-level system status change (idle, running, etc)."""
    event_type: str = SystemEventType.STATE_REFRESHED
    status: str = "idle"
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    def to_frontend_payload(self) -> dict:
        """Map to legacy StatusEvent format."""
        return {
            "type": "status",
            "thread_id": self.thread_id,
            "status": self.status
        }


class AppStartedEvent(BaseEvent):
    """Event published when the application starts."""
    event_type: str = SystemEventType.APP_STARTED
    is_public: bool = True
    broadcast_channel: str = "system"


class AppStoppingEvent(BaseEvent):
    """Event published when the application is stopping."""
    event_type: str = SystemEventType.APP_STOPPING
    is_public: bool = True
    broadcast_channel: str = "system"


class UserLoggedInEvent(BaseEvent):
    """Event published when a user logs in."""
    event_type: str = SystemEventType.USER_LOGGED_IN
    is_public: bool = True
    broadcast_channel: str = "system"


class UserLoggedOutEvent(BaseEvent):
    """Event published when a user logs out."""
    event_type: str = SystemEventType.USER_LOGGED_OUT
    is_public: bool = True
    broadcast_channel: str = "system"


class SystemLogEvent(BaseEvent):
    """Event representing a system log entry shared with the UI."""
    event_type: str = "system.log_entry"
    log_type: str = ""
    log_data: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None

    # Enable automatic bridging to UI
    is_public: bool = True
    broadcast_channel: str = "chat"

    def to_frontend_payload(self) -> dict:
        """Map to legacy system_log format."""
        return {
            "type": "system_log",
            "event": self.log_type,
            "data": self.log_data,
            "timestamp": self.timestamp.isoformat()
        }
