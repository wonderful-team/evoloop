"""Conversation rewind — perform_rewind() + event bus for cross-domain cleanup.

The rewind system has two parts:
1. perform_rewind() — deletes messages, clears HITL, then publishes RewindRequestedEvent
2. RewindRequestedEvent — 6 domains subscribe via @event_subscribe to do their own cleanup

The MESSAGES_CLEANUP event is also published for EvoCloud sync (separate subscriber).
"""

import logging
from typing import Any

from pydantic import Field, model_validator
from sqlalchemy import delete, func, select, update

from app.constants import MESSAGES_CLEANUP, REWIND_REQUESTED
from app.core.events import system_bus
from app.core.events.base import BaseEvent, EventData
from app.infrastructure.database import session_scope
from app.models import Message, MessageReference

logger = logging.getLogger(__name__)


# ───────────────────────── Event types ─────────────────────────


class RewindRequestedEvent(BaseEvent):
    """Published to trigger cross-domain cleanup (memory, file, learning, planning, evocloud).

    Subscribers read event.results to report counts.
    Pre-computed affected_message_ids prevents race conditions between handlers.
    """

    source: str = "rewind_service"
    thread_id: str = ""
    event_type: str = REWIND_REQUESTED
    target_message_id: str | None = None
    include_target: bool = False
    revert_files: bool = True
    reset_state: bool = True
    reason: str = "user_request"
    results: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    success: bool = True
    affected_message_ids: list[str] = Field(default_factory=list)
    affected_run_ids: list[str] = Field(default_factory=list)
    target_sequence: int = 0

    @model_validator(mode="after")
    def _build_data(self):
        self.data = EventData(
            thread_id=self.thread_id,
            target_message_id=self.target_message_id,
            include_target=self.include_target,
            revert_files=self.revert_files,
            reset_state=self.reset_state,
            reason=self.reason,
            affected_message_ids=self.affected_message_ids,
            affected_run_ids=self.affected_run_ids,
            target_sequence=self.target_sequence,
        )
        return self


class MessagesCleanupEvent(BaseEvent):
    """Published to trigger message deletion (used by EvoCloud sync + fallback entry)."""

    source: str = "rewind_service"
    thread_id: str = ""
    event_type: str = MESSAGES_CLEANUP
    message_ids: list[str] = Field(default_factory=list)
    delete_references: bool = True
    target_sequence: int = 0
    include_target: bool = False

    @model_validator(mode="after")
    def _build_data(self):
        self.data = EventData(
            thread_id=self.thread_id,
            message_ids=self.message_ids,
            count=len(self.message_ids),
            target_sequence=self.target_sequence,
            include_target=self.include_target,
        )
        return self


# ───────────────────────── Exceptions ─────────────────────────


class RewindError(Exception):
    def __init__(self, message: str, thread_id: str | None = None):
        super().__init__(message)
        self.thread_id = thread_id
        self.message = message


class MessageNotFoundError(RewindError):
    pass


class NoHumanMessageError(RewindError):
    pass


# ───────────────────────── Publishers ─────────────────────────


async def publish_messages_cleanup(
    thread_id: str,
    message_ids: list[str],
    delete_references: bool = True,
    target_sequence: int = 0,
    include_target: bool = False,
) -> None:
    """Publish a messages cleanup event (for EvoCloud sync + fallback entry)."""
    await system_bus.publish(
        MessagesCleanupEvent(
            thread_id=thread_id,
            message_ids=message_ids,
            delete_references=delete_references,
            target_sequence=target_sequence,
            include_target=include_target,
        )
    )


# ───────────────────────── Core ─────────────────────────


async def perform_rewind(
    thread_id: str,
    target_message_id: str | None = None,
    include_target: bool = True,
    revert_files: bool = True,
    reset_state: bool = False,
    reason: str = "user_request",
):
    """Rewind conversation: delete messages, clear HITL, publish event for cross-domain cleanup.

    Returns RewindResult.
    """
    from app.core.engine.schemas import RewindResult

    logger.info(
        f"[Rewind] thread={thread_id} target={target_message_id} "
        f"include_target={include_target} revert_files={revert_files}"
    )

    try:
        # Phase 0: Pre-compute affected message IDs (prevents race conditions)
        (
            affected_ids,
            affected_run_ids,
            target_seq,
        ) = await _compute_affected_message_ids(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=include_target,
        )

        # Phase 1: Delete messages + references (inline)
        deleted_count = await _delete_messages(affected_ids) if affected_ids else 0
        if deleted_count:
            from app.core.engine.message.sequence import SequenceService

            async with session_scope() as session:
                stmt = select(func.max(Message.sequence_number)).where(
                    Message.thread_id == thread_id
                )
                res = await session.execute(stmt)
                max_seq = res.scalar() or 0
                await SequenceService.set_sequence(thread_id, max_seq + 1)
            logger.info(
                f"[Rewind] Deleted {deleted_count} messages, seq reset to {max_seq + 1}"
            )

        # Phase 2: Clear HITL requests and activity status
        await _clear_hitl(thread_id)

        # Phase 3: Publish event for cross-domain cleanup (memory, file, learning, planning, evocloud)
        event = RewindRequestedEvent(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=include_target,
            revert_files=revert_files,
            reset_state=reset_state,
            reason=reason,
            affected_message_ids=affected_ids,
            affected_run_ids=affected_run_ids,
            target_sequence=target_seq,
        )
        await system_bus.publish(event, sequential=True, propagate_errors=True)

        # Phase 4: Publish messages cleanup for EvoCloud sync
        if affected_ids:
            await publish_messages_cleanup(
                thread_id=thread_id,
                message_ids=affected_ids,
                target_sequence=target_seq,
                include_target=include_target,
            )

        res = event.results
        result = RewindResult(
            status="success"
            if event.success and not event.errors
            else "partial_failure",
            thread_id=thread_id,
            removed_message_count=deleted_count,
            reverted_file_count=res.get("files", 0),
            removed_memory_count=res.get("memories", 0),
            removed_trace_count=res.get("traces", 0),
            checkpoint_id=None,
            errors=event.errors,
        )
        logger.info(f"[Rewind] Done: {result}")
        return result

    except Exception as e:
        if isinstance(e, RewindError):
            raise
        logger.exception(f"[Rewind] Failed for thread={thread_id}: {e}")
        raise RewindError(f"Rewind failed: {e}", thread_id=thread_id) from e


async def _compute_affected_message_ids(
    thread_id: str,
    target_message_id: str | None,
    include_target: bool,
) -> tuple[list[str], list[str], int]:
    """Pre-compute the list of message IDs, run IDs, and target sequence number."""
    async with session_scope() as session:
        stmt = select(Message.id, Message.sequence_number, Message.run_id).where(
            Message.thread_id == thread_id
        )

        if target_message_id:
            stmt_target = select(Message.sequence_number, Message.thread_id).where(
                Message.id == target_message_id
            )
            res_target = await session.execute(stmt_target)
            target = res_target.one_or_none()
            if target is None or target.thread_id != thread_id:
                logger.warning(f"[Rewind] Target message {target_message_id} not found")
                raise MessageNotFoundError(
                    f"Target message {target_message_id} not found in thread {thread_id}"
                )
            target_seq = target.sequence_number
            if include_target:
                stmt = stmt.where(Message.sequence_number >= target_seq)
            else:
                stmt = stmt.where(Message.sequence_number > target_seq)
        else:
            sub = (
                select(Message.sequence_number)
                .where(Message.thread_id == thread_id, Message.role == "human")
                .order_by(Message.sequence_number.desc())
                .limit(1)
            )
            result = await session.execute(sub)
            last_human_seq = result.scalar_one_or_none()
            if last_human_seq is not None:
                target_seq = last_human_seq
                stmt = stmt.where(Message.sequence_number >= last_human_seq)
            else:
                raise NoHumanMessageError(f"No human message found in thread {thread_id}")

        result = await session.execute(stmt)
        rows = result.all()
        message_ids = [str(row.id) for row in rows]
        run_ids = [row.run_id for row in rows if row.run_id]
        return message_ids, list(set(run_ids)), target_seq


async def _delete_messages(message_ids: list[str]) -> int:
    """Delete messages and their references."""
    if not message_ids:
        return 0
    async with session_scope() as session:
        await session.execute(
            delete(MessageReference).where(MessageReference.message_id.in_(message_ids))
        )
        await session.execute(
            update(Message)
            .where(Message.parent_id.in_(message_ids))
            .values(parent_id=None)
        )
        result = await session.execute(
            delete(Message).where(Message.id.in_(message_ids))
        )
        return result.rowcount


async def _clear_hitl(thread_id: str) -> None:
    """Clear activity status and cancel pending HITL requests."""
    try:
        from app.core.monitoring.activity import activity_monitor

        await activity_monitor.clear_human_request(thread_id)
    except Exception as e:
        logger.exception(f"[Rewind] Failed to clear activity: {e}")

    try:
        from app.core.hitl.core import cancel_request, get_pending_requests_for_thread

        pending = await get_pending_requests_for_thread(thread_id)
        for req in pending:
            await cancel_request(req.id)
        if pending:
            logger.info(f"[Rewind] Cancelled {len(pending)} pending HITL requests")
    except Exception as e:
        logger.exception(f"[Rewind] Failed to cancel HITL requests: {e}")
