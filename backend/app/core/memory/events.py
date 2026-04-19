"""
Memory-specific events for decoupled cross-domain communication.

These events allow domain layers (project, todo, etc.) to inject context
into memory operations without creating circular dependencies.
"""

from pydantic import Field

from app.core.events.base import BaseEvent, EventData

MEMORY_CONTEXT_GATHER_EVENT_TYPE = "memory.context_gather"


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

    event_type: str = MEMORY_CONTEXT_GATHER_EVENT_TYPE
    data: MemoryContextGatherData = Field(default_factory=MemoryContextGatherData)
