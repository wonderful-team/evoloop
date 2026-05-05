"""
Memory Event Schemas
====================

Pydantic data classes for memory-related events.
"""

from pydantic import Field

from app.core.engine.rewind.event import RewindEvent, RewindEventType
from app.core.events.base import BaseEvent, EventData


class MemoryContextGatherData(EventData):
    """Container for multi-source context fragments collected during memory extraction.

    Domain providers append pre-formatted markdown fragments via Jinja2 templates.
    Memory layer only joins them — no knowledge of domain-specific fields or formatting.
    """

    project_id: int | None = None
    context_fragments: list[str] = Field(default_factory=list)

    def to_context_string(self) -> str:
        """Join domain-formatted fragments into the final context string."""
        return "\n\n".join(self.context_fragments) if self.context_fragments else "No multi-source facts available."


class MemoryContextGatherEvent(BaseEvent):
    """
    Published by AutoMemoryExtractor to gather project context from domain modules.

    Domain handlers subscribe to this event and populate the data fields.
    The publisher awaits publish() completion, then reads the filled data.
    """

    event_type: str = "memory.context_gather"
    data: MemoryContextGatherData = Field(default_factory=MemoryContextGatherData)



