"""
Rewind Orchestrator
===================

Central coordinator for conversation rewinding operations.

This orchestrator uses an event-driven architecture where cleanup operations
are delegated to domain-specific handlers through the event bus.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.engine.rewind.events import (
    RewindFailedEvent,
    RewindRequestedEvent,
)
from app.core.engine.rewind.exceptions import (
    RewindError,
)
from app.core.engine.rewind.models import RewindResult
from app.core.events import system_bus

if TYPE_CHECKING:
    from app.core.events.base import AsyncEventBus

logger = logging.getLogger(__name__)


class RewindOrchestrator:
    """
    Orchestrates conversation rewinding through event-driven handlers.
    
    Responsibilities:
    1. Determine the scope of data to be rewound (message range)
    2. Publish events to trigger domain-specific cleanup handlers
    3. Coordinate LangGraph state rollback
    4. Collect results and report completion/failure
    
    Usage:
        orchestrator = RewindOrchestrator(event_bus=system_bus)
        result = await orchestrator.perform_rewind(
            thread_id="thread-123",
            target_message_id="msg-456",
            revert_files=True
        )
    """

    def __init__(self, event_bus: "AsyncEventBus" = None):
        """
        Initialize the rewind orchestrator.
        
        Args:
            event_bus: The event bus to use for publishing events.
                      Defaults to system_bus if not provided.
        """
        self.bus = event_bus or system_bus
        self._pending_results: dict[str, asyncio.Future] = {}

    async def perform_rewind(
        self,
        thread_id: str,
        target_message_id: str | None = None,
        include_target: bool = True,
        revert_files: bool = True,
        reset_state: bool = False,
        reason: str = "user_request"
    ) -> RewindResult:
        """
        Perform a rewind operation on the conversation.
        
        This method coordinates the entire rewind process:
        1. Publishes RewindRequestedEvent to trigger handlers
        2. Waits for all handlers to complete
        3. Handles LangGraph state rollback
        4. Returns a comprehensive result
        
        Args:
            thread_id: The thread to rewind
            target_message_id: Message ID to rewind to (None = last human message)
            include_target: Whether to delete the target message itself
            revert_files: Whether to revert file changes
            reset_state: Whether to reset LangGraph state
            reason: Why the rewind was triggered
            
        Returns:
            RewindResult with details of what was removed/reverted
            
        Raises:
            MessageNotFoundError: If target message doesn't exist
            NoHumanMessageError: If no human message exists to rewind to
            PartialRewindError: If some handlers failed but others succeeded
        """
        logger.info(
            f"[RewindOrchestrator] Starting rewind for thread={thread_id}, "
            f"target={target_message_id}, include_target={include_target}, "
            f"revert_files={revert_files}"
        )

        try:
            # Phase 1: Publish main rewind event
            # Handlers will subscribe to this and perform their cleanup
            rewind_event = RewindRequestedEvent(
                thread_id=thread_id,
                target_message_id=target_message_id,
                include_target=include_target,
                revert_files=revert_files,
                reset_state=reset_state,
                reason=reason
            )

            # Sequential=True is CRITICAL for SQLite to prevent 'Database is locked' errors
            # propagate_errors=True ensures we don't silently fail as requested by USER
            await self.bus.publish(rewind_event, sequential=True, propagate_errors=True)

            # Phase 2: Results are now aggregated in rewind_event.results by handlers
            # Since AsyncEventBus.publish awaits all handlers concurrently, 
            # we can safely read the results here.

            res = rewind_event.results
            result = RewindResult(
                status="success" if rewind_event.success and not rewind_event.errors else "partial_failure",
                thread_id=thread_id,
                removed_message_count=res.get("messages", 0),
                reverted_file_count=res.get("files", 0),
                removed_memory_count=res.get("memories", 0),
                removed_todo_count=res.get("todos", 0),
                removed_trace_count=res.get("traces", 0),
                new_checkpoint_id=res.get("checkpoint_id"),
                errors=rewind_event.errors
            )

            logger.info(
                f"[RewindOrchestrator] Rewind completed for thread={thread_id}. "
                f"Results: {res}, Errors: {rewind_event.errors}"
            )

            return result

        except Exception as e:
            logger.error(f"[RewindOrchestrator] Rewind failed for thread={thread_id}: {e}")

            # Publish failure event
            await self.bus.publish(RewindFailedEvent(
                thread_id=thread_id,
                error=str(e),
                failed_step="orchestrator"
            ))

            raise RewindError(
                message=f"Rewind operation failed: {e}",
                thread_id=thread_id
            ) from e
