"""
Todo Event Publishers
=====================

Helper functions for publishing todo-related events.
"""

from app.core.events import system_bus


async def publish_todo_cleanup(thread_id: str, source_message_ids: list[str]) -> None:
    """Publish a todo cleanup event for rewind operations."""
    from app.domain.todo.rewind import TodoCleanupEvent

    await system_bus.publish(
        TodoCleanupEvent(thread_id=thread_id, source_message_ids=source_message_ids)
    )
