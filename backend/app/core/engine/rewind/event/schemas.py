from app.core.events.base import BaseEvent


class RewindFailedEvent(BaseEvent):
    """Event published when a rewind operation fails."""

    event_type: str = "rewind.failed"
    thread_id: str = ""
    error: str = ""
