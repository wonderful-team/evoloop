"""
Macro Execution Event Publishers
================================

Helper functions for publishing macro execution events.
"""

from app.core.events import system_bus

from .schemas import MacroExecutionFailedEvent


async def publish_macro_execution_failed(
    skill_id: int | None,
    skill_name: str,
    error_message: str,
    fallback_context: dict | None,
    thread_id: str,
) -> MacroExecutionFailedEvent:
    """
    Publish a macro execution failed event.

    Returns the event instance so callers can read suggestions appended by listeners.
    """
    event = MacroExecutionFailedEvent(
        skill_id=skill_id,
        skill_name=skill_name,
        error_message=error_message,
        fallback_context=fallback_context,
        thread_id=thread_id,
    )
    await system_bus.publish(event)
    return event
