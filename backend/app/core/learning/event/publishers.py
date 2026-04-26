"""
Learning Event Publishers
=========================

Helper functions for publishing learning-related events.
"""

from app.core.events import system_bus


async def publish_trace_cleanup(thread_id: str, source_message_ids: list[str]) -> None:
    """Publish a trace cleanup event for rewind operations."""
    from app.core.learning.rewind import TraceCleanupEvent

    await system_bus.publish(
        TraceCleanupEvent(thread_id=thread_id, source_message_ids=source_message_ids)
    )
