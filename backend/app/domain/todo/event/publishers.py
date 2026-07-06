"""
Todo Event Publishers
=====================

Helper functions for publishing todo-related events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.events import system_bus

if TYPE_CHECKING:
    from app.domain.todo.event.schemas import TodoUpdatedEvent


async def publish_todo_updated(
    todo_id: str | None = None,
    action: str = "updated",
    project_id: int | None = None,
) -> TodoUpdatedEvent:
    """Publish a public TodoUpdatedEvent (bridged to frontend SSE)."""
    from app.domain.todo.event.schemas import TodoUpdatedEvent

    event = TodoUpdatedEvent(
        todo_id=todo_id,
        action=action,
        project_id=project_id,
    )
    await system_bus.publish(event)
    return event
