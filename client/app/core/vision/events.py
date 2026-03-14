from dataclasses import dataclass

from app.core.events.base import BaseEvent
from app.core.vision.types import VisionResult


@dataclass
class VisionEvent(BaseEvent):
    """Base class for vision events."""
    source: str = "vision_engine"


@dataclass
class VisionProcessStartedEvent(BaseEvent):
    """Triggered when a vision task starts."""
    event_type: str = "vision.process_started"


@dataclass
class VisionProcessCompletedEvent(BaseEvent):
    """Triggered when a vision task completes."""
    event_type: str = "vision.process_completed"
    result: VisionResult = None
