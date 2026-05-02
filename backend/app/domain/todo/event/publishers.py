"""
Todo Event Publishers
=====================

Helper functions for publishing todo-related events.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.events import system_bus

if TYPE_CHECKING:
    from app.domain.todo.event.schemas import TodoCleanupEvent


async def publish_todo_cleanup(
    thread_id: str,
    source_message_ids: list[str],
    affected_run_ids: list[str] | None = None
) -> TodoCleanupEvent:
    """Publish a TodoCleanupEvent to the system bus."""
    from app.domain.todo.event.schemas import TodoCleanupEvent

    event = TodoCleanupEvent(
        thread_id=thread_id,
        source_message_ids=source_message_ids,
        affected_run_ids=affected_run_ids or []
    )
    await system_bus.publish(event)
    return event
