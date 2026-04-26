"""
Rewind Event Publishers
=======================

Helper functions for publishing rewind events.
"""

from app.core.events import system_bus

from .schemas import RewindCompletedEvent, RewindFailedEvent, RewindRequestedEvent


async def publish_rewind_requested(
    thread_id: str,
    target_message_id: str | None = None,
    include_target: bool = False,
    revert_files: bool = True,
    reset_state: bool = True,
    reason: str = "user_request",
    affected_message_ids: list[str] | None = None,
    sequential: bool = False,
    propagate_errors: bool = False,
) -> RewindRequestedEvent:
    """Publish a rewind request event. Returns the event instance for result reading."""
    event = RewindRequestedEvent(
        thread_id=thread_id,
        target_message_id=target_message_id,
        include_target=include_target,
        revert_files=revert_files,
        reset_state=reset_state,
        reason=reason,
        affected_message_ids=affected_message_ids or [],
    )
    await system_bus.publish(event, sequential=sequential, propagate_errors=propagate_errors)
    return event


async def publish_rewind_completed(
    thread_id: str,
    removed_message_count: int = 0,
    reverted_file_count: int = 0,
    removed_memory_count: int = 0,
    new_checkpoint_id: str | None = None,
) -> None:
    """Publish a rewind completed event."""
    await system_bus.publish(
        RewindCompletedEvent(
            thread_id=thread_id,
            removed_message_count=removed_message_count,
            reverted_file_count=reverted_file_count,
            removed_memory_count=removed_memory_count,
            new_checkpoint_id=new_checkpoint_id,
        )
    )


async def publish_rewind_failed(
    thread_id: str,
    error: str = "",
    failed_step: str = "unknown",
    partial_results: dict | None = None,
) -> None:
    """Publish a rewind failed event."""
    await system_bus.publish(
        RewindFailedEvent(
            thread_id=thread_id,
            error=error,
            failed_step=failed_step,
            partial_results=partial_results or {},
        )
    )


async def publish_checkpoint_cleanup(
    thread_id: str,
    checkpoint_ids: list[str],
    min_checkpoint_id: str | None = None,
) -> None:
    """Publish a checkpoint cleanup event for rewind operations."""
    from app.core.engine.rewind.event.schemas import CheckpointCleanupEvent

    await system_bus.publish(
        CheckpointCleanupEvent(
            thread_id=thread_id,
            checkpoint_ids=checkpoint_ids,
            min_checkpoint_id=min_checkpoint_id,
            delete_data=True,
        )
    )


async def publish_messages_cleanup(
    thread_id: str,
    message_ids: list[str],
    delete_references: bool = True,
) -> None:
    """Publish a messages cleanup event for rewind operations."""
    from app.core.engine.rewind.event.schemas import MessagesCleanupEvent

    await system_bus.publish(
        MessagesCleanupEvent(
            thread_id=thread_id,
            message_ids=message_ids,
            delete_references=delete_references,
        )
    )
