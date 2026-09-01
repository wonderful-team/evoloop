"""
Vision Event Schemas
====================

Pydantic data classes for vision events.
"""

from app.core.events.base import BaseEvent
from app.infrastructure.vision.types import VisionResult

from .types import VisionEventType


class VisionEvent(BaseEvent):
    """Base class for vision events."""

    source: str = "vision_engine"


class VisionProcessStartedEvent(VisionEvent):
    """Triggered when a vision task starts."""

    event_type: str = VisionEventType.PROCESS_STARTED


class VisionProcessCompletedEvent(VisionEvent):
    """Triggered when a vision task completes."""

    event_type: str = VisionEventType.PROCESS_COMPLETED
    result: VisionResult = None
