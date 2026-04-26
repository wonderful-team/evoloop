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
        project_id=project_id,
        data=MemoryContextGatherData(project_id=project_id),
    )
    await system_bus.publish(event, sequential=True)
    return event


async def publish_memory_cleanup(
    thread_id: str, source_message_ids: list[str], run_ids: list[str] | None = None
) -> None:
    """Publish a memory cleanup event for rewind operations."""
    from app.core.memory.event.schemas import MemoryCleanupEvent

    await system_bus.publish(
        MemoryCleanupEvent(
            thread_id=thread_id,
            source_message_ids=source_message_ids,
            run_ids=run_ids or [],
        )
    )
