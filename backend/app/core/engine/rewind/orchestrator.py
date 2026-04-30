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

from app.core.engine.rewind.exceptions import (
    RewindError,
)
from app.core.engine.schemas import RewindResult
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
            # Phase 0: Pre-compute affected message IDs.
            # This prevents race conditions where MessageRewind deletes rows
            # before TodoRewind/TraceRewind/FileRewind can query them.
            affected_ids, affected_run_ids = await self._compute_affected_message_ids(
                thread_id=thread_id,
                target_message_id=target_message_id,
                include_target=include_target
            )

            # Phase 1: Publish main rewind event
            # Handlers will subscribe to this and perform their cleanup
            # Sequential=True is CRITICAL for SQLite to prevent 'Database is locked' errors
            # propagate_errors=True ensures we don't silently fail as requested by USER
            from app.core.engine.rewind.event.publishers import publish_rewind_requested
            rewind_event = await publish_rewind_requested(
                thread_id=thread_id,
                target_message_id=target_message_id,
                include_target=include_target,
                revert_files=revert_files,
                reset_state=reset_state,
                reason=reason,
                affected_message_ids=affected_ids,
                affected_run_ids=affected_run_ids,
                sequential=True,
                propagate_errors=True,
            )

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
                checkpoint_id=res.get("checkpoint_id"),
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
            from app.core.engine.rewind.event.publishers import publish_rewind_failed
            await publish_rewind_failed(
                thread_id=thread_id,
                error=str(e),
                failed_step="orchestrator",
            )

            raise RewindError(
                message=f"Rewind operation failed: {e}",
                thread_id=thread_id
            ) from e

    async def _compute_affected_message_ids(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> tuple[list[str], list[str]]:
        """
        Pre-compute the list of message IDs and run IDs that will be affected by this rewind.
        """
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

        async with session_scope() as session:
            # Query sequence_number and run_id
            stmt = select(Message.sequence_number, Message.run_id).where(Message.thread_id == thread_id)

            if target_message_id:
                try:
                    # Handle "msg-{thread_id}-{sequence_number}" format or raw ID
                    t_seq = target_message_id
                    if t_seq.startswith("msg-"):
                        parts = t_seq.split("-")
                        if len(parts) >= 3:
                            t_seq = parts[-1]
                        target_seq = int(t_seq)
                    else:
                        # If it's a raw integer string, it might be a database ID
                        # Let's check if a message exists with this ID first
                        if t_seq.isdigit():
                            msg_id = int(t_seq)
                            id_stmt = select(Message.sequence_number).where(Message.id == msg_id)
                            id_res = await session.execute(id_stmt)
                            found_seq = id_res.scalar_one_or_none()
                            if found_seq is not None:
                                target_seq = found_seq
                                logger.info(f"[RewindOrchestrator] Resolved ID {msg_id} to sequence_number {target_seq}")
                            else:
                                # Fallback: treat as sequence number
                                target_seq = int(t_seq)
                        else:
                            target_seq = int(t_seq)

                    logger.info(f"[RewindOrchestrator] Using target_sequence: {target_seq} (from {target_message_id})")
                    
                    if include_target:
                        stmt = stmt.where(Message.sequence_number >= target_seq)
                    else:
                        stmt = stmt.where(Message.sequence_number > target_seq)
                except (ValueError, TypeError):
                    logger.warning(f"[RewindOrchestrator] Invalid target_message_id: {target_message_id}")
                    return [], []
            else:
                # No target specified – find last human message and use it as anchor
                sub = (
                    select(Message.sequence_number)
                    .where(Message.thread_id == thread_id, Message.role == "human")
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )
                result = await session.execute(sub)
                last_human_seq = result.scalar_one_or_none()
                if last_human_seq is not None:
                    stmt = stmt.where(Message.sequence_number >= last_human_seq)
                else:
                    return [], []

            result = await session.execute(stmt)
            rows = result.all()
            
            message_ids = [f"msg-{thread_id}-{row.sequence_number}" for row in rows]
            run_ids = [row.run_id for row in rows if row.run_id]
            
            # Return unique run_ids
            return message_ids, list(set(run_ids))
