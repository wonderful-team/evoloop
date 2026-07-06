"""
Learning Event Schemas
======================

Pydantic data classes for learning domain events.
"""

from app.core.events.base import BaseEvent

from .types import LearningEventType


class SynthesisCompletedEvent(BaseEvent):
    """
    Public event published when a smart synthesis job completes or fails.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = LearningEventType.SYNTHESIS_COMPLETED
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
