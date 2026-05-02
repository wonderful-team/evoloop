"""
Learning Event Publishers
=========================

Helper functions for publishing learning-related events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.events import system_bus

if TYPE_CHECKING:
    from app.core.learning.event.schemas import TraceCleanupEvent


async def publish_trace_cleanup(
    thread_id: str,
    source_message_ids: list[str],
    affected_run_ids: list[str] | None = None
) -> TraceCleanupEvent:
    """Publish a TraceCleanupEvent to the system bus."""
    from app.core.learning.event.schemas import TraceCleanupEvent

    event = TraceCleanupEvent(
        thread_id=thread_id,
        source_message_ids=source_message_ids,
        affected_run_ids=affected_run_ids or []
    )
    await system_bus.publish(event)
    return event
