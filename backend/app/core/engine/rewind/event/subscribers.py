"""
Rewind Event Subscribers
========================

Event-driven cleanup handlers for conversation rewind operations.
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage
from sqlalchemy import delete, select, update, func

from app.core.engine.rewind.checkpoint_repository import CheckpointRepository
from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.core.engine.rewind.event.schemas import CheckpointCleanupEvent
from app.core.engine.rewind.event.schemas import MessagesCleanupEvent
from app.core.engine.rewind.exceptions import MessageNotFoundError, NoHumanMessageError
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe, register_instance_handlers
from app.core.globals import get_graph
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, MessageReference

logger = logging.getLogger(__name__)


@event_register()
class CheckpointRewind:
    """
    Event-driven checkpoint cleanup handler for rewind operations.

    Handles deletion of LangGraph checkpoint data from SQLite:
    - checkpoints table: Main checkpoint records
    - writes table: Task writes (langgraph-checkpoint-sqlite)
    - checkpoint_blobs table: Blob storage
    """

    def __init__(self):
        self._deleted_checkpoints = 0
        self._deleted_writes = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "CheckpointRewind":
        """
        Register this handler to the event bus.

        Args:
            bus: The event bus to subscribe to

        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare checkpoint cleanup.

        Determines the checkpoint range to delete and publishes cleanup event.
        """
        # Find checkpoints to delete based on message range
        checkpoint_info = await self._find_checkpoints_to_delete(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target,
            reason=event.reason
        )

        if checkpoint_info:
            checkpoint_ids, min_checkpoint_id = checkpoint_info

            # Perform deletion directly to capture count for aggregation
            count = await self._delete_checkpoints(
                thread_id=event.thread_id,
                checkpoint_ids=checkpoint_ids
            )

            # Report back to the main event
            event.results["checkpoints"] = count

            # Still publish specific cleanup event for other potential listeners
            from app.core.engine.rewind.event.publishers import publish_checkpoint_cleanup
            await publish_checkpoint_cleanup(
                thread_id=event.thread_id,
                checkpoint_ids=checkpoint_ids,
                min_checkpoint_id=min_checkpoint_id,
            )
            logger.info(f"[CheckpointRewind] Deleted {count} checkpoints for thread {event.thread_id}")
        else:
            logger.debug(f"[CheckpointRewind] No checkpoints found to delete for thread {event.thread_id}")

    @event_subscribe(RewindEventType.CHECKPOINT_CLEANUP)
    async def _handle_checkpoint_cleanup(self, event: CheckpointCleanupEvent) -> None:
        """
        Handle specific checkpoint cleanup event.

        Deletes checkpoint records from SQLite tables.
        """
        try:
            count = await self._delete_checkpoints(
                thread_id=event.thread_id,
                checkpoint_ids=event.checkpoint_ids,
                min_checkpoint_id=event.min_checkpoint_id,
            )
            self._deleted_checkpoints = count
            logger.info(f"[CheckpointRewind] Deleted {count} checkpoints and {self._deleted_writes} writes")
        except Exception as e:
            logger.error(f"[CheckpointRewind] Checkpoint cleanup failed: {e}")
            # Don't raise - checkpoint cleanup is best-effort

    async def _find_checkpoints_to_delete(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool,
        reason: str = "user_request"
    ) -> tuple[list[str], str | None] | None:
        """Find checkpoint IDs to delete based on message range.

        For retry operations, deletes ALL checkpoints to ensure a clean slate.
        For targeted rewind, finds the checkpoint matching the target message.
        """
        try:
            rows = await CheckpointRepository.find_checkpoints_ordered_by_step(thread_id)
            if not rows:
                return None

            all_ids = [row[0] for row in rows]
            checkpoint_info = []
            for row in rows:
                cp_id = row[0]
                meta = CheckpointRepository.parse_metadata(row[1])
                checkpoint_info.append({
                    "id": cp_id,
                    "step": meta.get("step", 0),
                    "source": meta.get("source", ""),
                    "run_id": meta.get("run_id", ""),
                })

            # Retry mode: keep the latest checkpoint (needed for StateRewind rollback),
            # delete all older checkpoints to ensure a clean restart.
            if reason == "retry" or not target_message_id:
                if len(all_ids) <= 1:
                    return None
                latest_id = checkpoint_info[0]["id"]
                ids_to_delete = [c["id"] for c in checkpoint_info[1:]]
                return (ids_to_delete, latest_id) if ids_to_delete else None

            # Targeted rewind mode
            target_checkpoint = None
            for c in checkpoint_info:
                if target_message_id in c["id"] or c["id"] in target_message_id:
                    target_checkpoint = c["id"]
                    break

            if not target_checkpoint:
                target_checkpoint = checkpoint_info[0]["id"]

            try:
                target_idx = all_ids.index(target_checkpoint)
                ids_to_delete = all_ids[:target_idx + 1] if include_target else all_ids[:target_idx]
            except ValueError:
                ids_to_delete = []

            return (ids_to_delete, target_checkpoint) if ids_to_delete else None

        except Exception as e:
            logger.warning(f"[CheckpointRewind] Failed to find checkpoints: {e}")
            return None

    async def _delete_checkpoints(
        self,
        thread_id: str,
        checkpoint_ids: list[str],
        min_checkpoint_id: str | None = None,
    ) -> int:
        """Delete checkpoints and associated writes from the active database."""
        if not checkpoint_ids and not min_checkpoint_id:
            return 0

        try:
            deleted_checkpoints, deleted_writes = await CheckpointRepository.delete_checkpoints_and_writes(
                thread_id, checkpoint_ids
            )
            self._deleted_writes = deleted_writes
            logger.info(f"[CheckpointRewind] Deleted {deleted_checkpoints} checkpoints and {deleted_writes} writes")
            return deleted_checkpoints
        except Exception as e:
            logger.error(f"[CheckpointRewind] Failed to delete checkpoints: {e}")
            return 0

    async def cleanup(
        self,
        thread_id: str,
        checkpoint_ids: list[str] | None = None,
        min_checkpoint_id: str | None = None,
    ) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_checkpoints(
            thread_id=thread_id,
            checkpoint_ids=checkpoint_ids or [],
            min_checkpoint_id=min_checkpoint_id,
        )

    def get_deleted_counts(self) -> tuple[int, int]:
        """Get the counts of deleted checkpoints and writes."""
        return (self._deleted_checkpoints, self._deleted_writes)


@event_register()
class MessageRewind:
    """Event-driven message cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "MessageRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - determine message range and trigger cleanup.
        
        Uses event.affected_message_ids (pre-computed by RewindOrchestrator)
        to avoid race conditions with other handlers querying the messages table.
        """
        # Use pre-computed message IDs (UUIDs) if available, otherwise fall back to query
        message_ids = event.affected_message_ids or await self._find_messages_to_delete(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target
        )

        if message_ids:
            count = await self._delete_messages(
                message_ids=message_ids,
                delete_references=True
            )
            self._deleted_count = count
            event.results["messages"] = count

            # 3. Reset sequence counter to maintain continuity
            from app.core.engine.message.sequence import SequenceService
            async with session_scope() as session:
                # Find max sequence remaining in the DB
                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == event.thread_id)
                res = await session.execute(stmt)
                max_seq = res.scalar() or 0
                await SequenceService.set_sequence(event.thread_id, max_seq + 1)

            from app.core.engine.rewind.event.publishers import publish_messages_cleanup
            await publish_messages_cleanup(
                thread_id=event.thread_id,
                message_ids=message_ids,
                delete_references=True,
            )
            logger.info(f"[MessageRewind] Deleted {count} messages and reset sequence to {max_seq + 1} for thread {event.thread_id}")
        else:
            logger.info(f"[MessageRewind] No messages to delete for thread {event.thread_id}")

    @event_subscribe(RewindEventType.MESSAGES_CLEANUP)
    async def _handle_messages_cleanup(self, event: MessagesCleanupEvent) -> None:
        """
        Handle specific message cleanup event.
        
        This performs the actual message and reference deletion.
        """
        try:
            count = await self._delete_messages(
                message_ids=event.message_ids,
                delete_references=event.delete_references
            )
            self._deleted_count = count
            logger.info(f"[MessageRewind] Deleted {count} messages and their references")
        except Exception as e:
            logger.error(f"[MessageRewind] Message cleanup failed: {e}")
            raise

    async def _find_messages_to_delete(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Find the range of messages to delete.
        
        Args:
            thread_id: The thread ID
            target_message_id: The message to rewind to (None = last human message)
            include_target: Whether to include the target message in deletion
        """
        async with session_scope() as session:
            if target_message_id:
                try:
                    # target_message_id is now a UUID
                    target_stmt = select(Message).where(Message.id == target_message_id)
                    result = await session.execute(target_stmt)
                    target_msg = result.scalar_one_or_none()

                    if not target_msg:
                        raise MessageNotFoundError(f"Target message {target_message_id} not found", thread_id=thread_id)

                    min_id_to_delete = target_msg.id
                except (ValueError, TypeError):
                    logger.error(f"[MessageRewind] Invalid target message ID: {target_message_id}")
                    return []
            else:
                # Find last human message
                stmt = (
                    select(Message.id)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "human")
                    .order_by(Message.id.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                last_human = result.scalar_one_or_none()
                if not last_human:
                    raise NoHumanMessageError("No human message found to rewind to", thread_id=thread_id)

                min_id_to_delete = last_human.id

            # Query all messages to delete
            if include_target:
                stmt = select(Message.id).where(
                    Message.thread_id == thread_id,
                    Message.id >= min_id_to_delete
                )
            else:
                stmt = select(Message.id).where(
                    Message.thread_id == thread_id,
                    Message.id > min_id_to_delete
                )

            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_messages(
        self,
        message_ids: list[str],
        delete_references: bool = True
    ) -> int:
        """
        Delete messages and optionally their references.
        
        Args:
            message_ids: List of message IDs to delete
            delete_references: Whether to delete MessageReference records
            
        Returns:
            Number of messages deleted
        """
        if not message_ids:
            return 0

        # IDs are now UUID strings
        if not message_ids:
            return 0

        async with session_scope() as session:
            # 1. Delete references first (if requested)
            if delete_references:
                ref_result = await session.execute(
                    delete(MessageReference)
                    .where(MessageReference.message_id.in_(message_ids))
                )
                logger.debug(f"[MessageRewind] Deleted {ref_result.rowcount} references")

            # 2. Update parent_id for messages pointing to deleted messages
            # This prevents foreign key constraint issues
            await session.execute(
                update(Message)
                .where(Message.parent_id.in_(message_ids))
                .values(parent_id=None)
            )

            # 3. Delete messages
            msg_result = await session.execute(
                delete(Message).where(Message.id.in_(message_ids))
            )

            deleted_count = msg_result.rowcount
            logger.info(f"🗑️ Deleted {deleted_count} Message records")
            return deleted_count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        delete_references = kwargs.get("delete_references", True)
        return await self._delete_messages(message_ids, delete_references)

    def get_deleted_count(self) -> int:
        """Get the count of messages deleted in the last operation."""
        return self._deleted_count


@event_register()
class StateRewind:
    """
    Handles LangGraph state rollback when conversation is rewound.
    
    This handler subscribes to rewind events and:
    1. Discovers the appropriate checkpoint for the target state
    2. Rolls back the LangGraph state to that checkpoint
    3. Resets blackboard and iteration count if requested
    
    Usage:
        StateRewind.register(system_bus)
    """

    def __init__(self):
        self._last_checkpoint_id: str | None = None

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "StateRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - perform checkpoint rollback.
        
        For retry operations, finds the oldest clean checkpoint and resets state.
        For targeted rewind, rolls back to the checkpoint matching the target message.
        """
        # Perform checkpoint rollback
        checkpoint_id = await self._rollback_to_checkpoint(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            reset_state=event.reset_state,
            include_target=event.include_target,
            reason=event.reason
        )

        self._last_checkpoint_id = checkpoint_id

        if checkpoint_id:
            event.results["checkpoint_id"] = checkpoint_id
            logger.info(f"[StateRewind] Rolled back to checkpoint {checkpoint_id}")
        else:
            logger.warning("[StateRewind] No matching checkpoint found")

    async def _rollback_to_checkpoint(
        self,
        thread_id: str,
        target_message_id: str | None,
        reset_state: bool,
        include_target: bool = True,
        reason: str = "user_request"
    ) -> str | None:
        """
        Rollback LangGraph to the appropriate checkpoint.
        
        For retry: finds the oldest 'input' checkpoint and prunes all polluted messages.
        For targeted rewind: attempts to find the checkpoint closest to the target message.
        
        Args:
            thread_id: The thread ID
            target_message_id: The target message (None = last human)
            reset_state: Whether to reset blackboard/iteration
            reason: Why the rewind was triggered
            
        Returns:
            The checkpoint ID after rollback, or None if not found
        """
        graph = get_graph()
        if not graph:
            logger.warning("[StateRewind] Graph not available")
            return None

        config = {"configurable": {"thread_id": thread_id}}

        # Search through checkpoint history (newest first)
        historical_states = []
        try:
            async for state_snapshot in graph.aget_state_history(config):
                historical_states.append(state_snapshot)
        except Exception as e:
            logger.warning(f"[StateRewind] Failed to get state history: {e}")
            return None

        if not historical_states:
            logger.warning("[StateRewind] No checkpoint history found")
            return None

        checkpoint_id = None
        base_state = None
        graph_updates = []

        # ------------------------------------------------------------------
        # Unified strategy: Find checkpoint containing target message,
        # remove target and all messages after it, keep everything before.
        # For retry (include_target=False), the target human message itself
        # is kept; only messages after it are removed.
        # ------------------------------------------------------------------
        target_sequence = await self._get_target_human_sequence(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=True
        )

        if not target_sequence:
            logger.warning("[StateRewind] No target sequence found")
            return None

        target_anchor = self._normalize_for_match(self._extract_text(target_sequence[-1]))

        found_target = False
        for state_snapshot in historical_states:
            sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []

            for m in sn_msgs:
                if isinstance(m, HumanMessage) and target_anchor:
                    msg_text = self._normalize_for_match(self._extract_text(m.content))
                    if msg_text == target_anchor:
                        found_target = True
                        if include_target and m.id:
                            graph_updates.append(RemoveMessage(id=m.id))
                        continue

                if found_target and m.id:
                    graph_updates.append(RemoveMessage(id=m.id))

            if found_target:
                checkpoint_id = state_snapshot.config.get("configurable", {}).get("checkpoint_id")
                base_state = state_snapshot
                logger.info(
                    f"[StateRewind] Found checkpoint {checkpoint_id} with target, "
                    f"removing {len(graph_updates)} messages (after target, include_target={include_target})"
                )
                break

        if not found_target:
            latest = historical_states[0]
            checkpoint_id = latest.config.get("configurable", {}).get("checkpoint_id")
            base_state = latest
            sn_msgs = base_state.values.get("messages", []) if base_state.values else []

            last_human_idx = -1
            for i, m in enumerate(sn_msgs):
                if isinstance(m, HumanMessage):
                    last_human_idx = i

            if last_human_idx >= 0:
                for m in sn_msgs[last_human_idx:]:
                    graph_updates.append(RemoveMessage(id=m.id))

            logger.info(
                f"[StateRewind] Target not found in checkpoints, using latest {checkpoint_id}. "
                f"Removing {len(graph_updates)} messages from last human onward."
            )

        # ------------------------------------------------------------------
        # Apply updates
        # ------------------------------------------------------------------
        if checkpoint_id and base_state:
            updates: dict[str, Any] = {}
            if graph_updates:
                updates["messages"] = graph_updates

            if reset_state:
                # Reset blackboard turn keys
                new_bb = base_state.values.get("blackboard", {}).copy() if base_state.values else {}
                turn_keys_to_reset = [
                    "ticket", "verification", "route_reason", "next_node",
                    "situation_analysis", "action_plan", "error", "spawn_plan",
                    "pending_aggregation", "plan_approved"
                ]
                for key in turn_keys_to_reset:
                    new_bb[key] = None

                updates.update({
                    "blackboard": new_bb,
                    "iteration_count": 0,
                    "current_plan": None,
                    "structured_plan": None,
                    "next_node": None,
                    "situation_analysis": None,
                    "action_plan": None,
                    "error": None
                })

            try:
                updated_config = await graph.aupdate_state(base_state.config, updates, as_node="__start__")
                if updated_config and "configurable" in updated_config:
                    new_checkpoint_id = updated_config["configurable"].get("checkpoint_id")
                    if new_checkpoint_id:
                        logger.info(f"[StateRewind] State updated to new checkpoint: {new_checkpoint_id}")
                        return new_checkpoint_id
            except Exception as e:
                logger.error(f"[StateRewind] Failed to update state: {e}")

        return checkpoint_id

    async def _get_target_human_sequence(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Get the human message sequence up to the target from the DB.
        
        Args:
            thread_id: The thread ID
            target_message_id: The target message (None = last human)
            include_target: Whether to include the target
            
        Returns:
            List of human message contents
        """
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .where(Message.role == "human")
                .order_by(Message.id.asc())
            )

            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(Message.id == target_message_id)
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()
                
                if target_seq is None:
                    # Fallback or error
                    logger.warning(f"[StateRewind] Could not resolve sequence for message {target_message_id}")
                    return []

                if include_target:
                    stmt = stmt.where(Message.sequence_number <= target_seq)
                else:
                    stmt = stmt.where(Message.sequence_number < target_seq)

            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [self._extract_text(m.content) for m in messages]

    def _extract_text(self, content) -> str:
        """Extract text from various content formats."""
        if not content:
            return ""

        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")

        # Recursive extraction for nested data structures
        if isinstance(content, list):
            return "".join([self._extract_text(item) for item in content])

        if isinstance(content, dict):
            # Try specific keys in order of likelihood
            for key in ["text", "content", "reasoning", "thought"]:
                if key in content:
                    return self._extract_text(content[key])
            # Fallback: join all string values
            return "".join([str(v) for v in content.values() if isinstance(v, (str, list, dict))])

        if isinstance(content, str):
            content = content.strip()
            if (content.startswith("{") and content.endswith("}")) or \
               (content.startswith("[") and content.endswith("]")):
                try:
                    parsed = json.loads(content)
                    return self._extract_text(parsed)
                except (json.JSONDecodeError, TypeError, ValueError):
                    # If JSON parsing fails, use regex as a fallback to grab anything in 'text' fields
                    text_matches = re.findall(r'["\']text["\']:\s*["\'](.*?)["\']', content)
                    if text_matches:
                        return "".join(text_matches).strip()
            return content

        return str(content)

    def _normalize_for_match(self, text: str) -> str:
        """Final normalization for sequence comparison."""
        if not text:
            return ""
        # Remove ALL whitespace, system tags, and common delimiters to get a pure 'fingerprint'
        text = re.sub(r'\[CONTEXT UPDATE.*?\]', '', text) # Remove system injection noise
        text = re.sub(r'[\s\n\r\t.,!?;:\(\)\[\]{}"\']+', '', text)
        return text.lower()

    def get_last_checkpoint_id(self) -> str | None:
        """Get the checkpoint ID from the last rollback operation."""
        return self._last_checkpoint_id
