"""
Event schemas for system-wide lifecycle events.
"""
from typing import Any, List, Optional
from langchain_core.messages import BaseMessage
from pydantic import Field, BaseModel

from app.core.events.base import BaseEvent, EventData
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
    original_skill_id: Optional[Any] = None
    ticket_topic: Optional[str] = None
    ticket_reason: Optional[str] = None


class SessionCompletedEvent(BaseEvent):
    """Event published when an agent session reaches a successful conclusion."""
    event_type: str = SystemEventType.SESSION_COMPLETED
    data: SessionCompletedData
