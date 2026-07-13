from app.core.engine.rewind.rewind import RewindRequestedEvent
from app.core.events import system_bus


async def publish_rewind_requested(
    thread_id: str,
    target_message_id: str | None = None,
    include_target: bool = False,
    revert_files: bool = True,
    reset_state: bool = True,
    reason: str = "user_request",
    affected_message_ids: list[str] = None,
    affected_run_ids: list[str] = None,
    target_sequence: int = 0,
    sequential: bool = True,
    propagate_errors: bool = True,
):
    """Helper to publish rewind requested event to system_bus."""
    event = RewindRequestedEvent(
        thread_id=thread_id,
        target_message_id=target_message_id,
        include_target=include_target,
        revert_files=revert_files,
        reset_state=reset_state,
        reason=reason,
        affected_message_ids=affected_message_ids or [],
        affected_run_ids=affected_run_ids or [],
        target_sequence=target_sequence,
    )
    await system_bus.publish(event, sequential=sequential, propagate_errors=propagate_errors)
    return event
