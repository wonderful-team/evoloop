from app.core.events.base import BaseEvent
from app.core.vision.types import VisionResult


class VisionEvent(BaseEvent):
    """Base class for vision events."""
    source: str = "vision_engine"


class VisionProcessStartedEvent(VisionEvent):
    """Triggered when a vision task starts."""
    event_type: str = "vision.process_started"


class VisionProcessCompletedEvent(VisionEvent):
    """Triggered when a vision task completes."""
    event_type: str = "vision.process_completed"
    result: VisionResult = None
