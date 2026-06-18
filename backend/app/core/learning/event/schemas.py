"""
Learning Event Schemas
======================

Pydantic data classes for learning domain events.
"""

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType
from app.core.events.base import BaseEvent


class TraceCleanupEvent(RewindEvent):
    """Published to trigger trace event deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    affected_run_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.TRACE_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "affected_run_ids": self.affected_run_ids,
            "count": len(self.source_message_ids),
        }


class SynthesisCompletedEvent(BaseEvent):
    """
    Public event published when a smart synthesis job completes or fails.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = "synthesis.completed"
    source: str = "learning"
    job_id: int
    status: str  # completed / failed
    skill_id: int | None = None
    session_id: str | None = None
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context) -> None:
        self.data = {
            "job_id": self.job_id,
            "status": self.status,
            "skill_id": self.skill_id,
            "session_id": self.session_id,
        }
