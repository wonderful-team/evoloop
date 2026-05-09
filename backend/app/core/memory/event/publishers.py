"""
Memory Event Publishers
=======================

Helper functions for publishing memory-related events.
"""

from app.core.events import system_bus

from .schemas import MemoryContextGatherData, MemoryContextGatherEvent


async def publish_memory_context_gather(
    project_id: int | None,
) -> MemoryContextGatherEvent:
    """
    Publish a context gather event and await domain handlers to fill data fields.

    Returns the event instance so callers can read the populated data.
    """
    event = MemoryContextGatherEvent(
        data=MemoryContextGatherData(project_id=project_id),
    )
    await system_bus.publish(event, sequential=True)
    return event



