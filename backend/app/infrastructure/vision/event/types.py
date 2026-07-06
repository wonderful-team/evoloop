"""
Vision Event Types
==================

Event type constants for vision processing.
"""

from enum import Enum


class VisionEventType(str, Enum):
    """Vision processing event types."""
    PROCESS_STARTED = "vision.process_started"
    PROCESS_COMPLETED = "vision.process_completed"
