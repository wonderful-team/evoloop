"""
MessageRepository — Database persistence and query operations for messages.

Extracted from MessageHandler to separate persistence concerns from orchestration.
"""
import logging
import uuid
import json

from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from app.core.engine.message.sequence import SequenceService
from app.infrastructure.database.sql.database import session_scope
from app.models import Message

logger = logging.getLogger(__name__)


class MessageRepository:
    """
    Handles all database operations for messages:
    - INSERT (persistence)
    - SELECT (query tool inputs, history)
    """

    def __init__(self, thread_id: str, project_id: int | None = None, run_id: str | None = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id

    async def persist(
        self,
        role: str,
        content: str | None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        action_type: str = "text",
        status: str = "completed",
        is_visible: bool = True,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        content_type: str = "text",
        metadata: dict | None = None,
        parent_id: str | None = None,
    ) -> tuple[str | None, int]:
        """
        Persist a message to the database.

        Returns:
            (message_id, sequence_number) or (None, 0) on failure
        """
        # Allow empty content for running tool steps (pre-inserted before execution)
        if not content and not thinking and not tool_calls and status != "running":
            logger.warning(f"[MessageRepository] Skipping persist for {role}: no content, thinking, or tool_calls")
            return None, 0

        try:
            seq = await SequenceService.next_sequence(self.thread_id)
            
            # Resolve parent_id if not provided
            effective_parent_id = parent_id
            if not effective_parent_id:
                effective_parent_id = await self.get_last_message_id()
                
            logger.info(f"[MessageRepository] Persisting {role} message (seq={seq}, cat={category}, parent={effective_parent_id})")

            async with session_scope() as session:
                log = Message(
                    id=str(uuid.uuid4()),
                    thread_id=self.thread_id,
                    project_id=self.project_id,
                    role=role,
                    content=content or "",
                    thinking=thinking,
                    sequence_number=seq,
                    run_id=self.run_id,
                    status=status,
                    category=category,
                    content_type=content_type,
                    action_type=action_type,
                    is_visible=is_visible,
                    tool_calls=tool_calls,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    meta_data=metadata,
                    parent_id=effective_parent_id,
                )
                session.add(log)
                await session.flush()

            return log.id, seq

        except Exception as e:
            logger.error(f"[MessageRepository] Failed to persist message: {e}")
            raise

    async def update(self, sequence_number: int, **fields) -> bool:
        """
        Update an existing message by sequence_number.

        Args:
            sequence_number: The sequence_number of the message to update
            **fields: Fields to update (e.g. status="completed", content="...")

        Returns:
            True if updated, False if message not found
        """
        try:
            async with session_scope() as session:
                from app.models import Message
                stmt = select(Message).where(
                    Message.thread_id == self.thread_id,
                    Message.sequence_number == sequence_number
                )
                result = await session.execute(stmt)
                msg = result.scalar_one_or_none()
                if not msg:
                    logger.warning(f"[MessageRepository] Message not found for update: thread={self.thread_id}, seq={sequence_number}")
                    return False

                for key, value in fields.items():
                    if hasattr(msg, key):
                        setattr(msg, key, value)
                    else:
                        logger.warning(f"[MessageRepository] Unknown field '{key}' on Message, skipping")

                await session.flush()
                logger.info(f"[MessageRepository] Updated message seq={sequence_number}: {fields.keys()}")
                return True

        except Exception as e:
            logger.error(f"[MessageRepository] Failed to update message seq={sequence_number}: {e}")
            raise

    async def resolve_tool_input(self, tool_call_id: str | None) -> dict:
        """
        Resolve tool input arguments from the most recent AI message's tool_calls.

        Returns:
            dict: Tool input args, empty dict if not found
        """
        if not tool_call_id:
            return {}
        try:
            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.role == "ai")
                    .where(Message.tool_calls.is_not(None))
                    .order_by(desc(Message.sequence_number))
                    .limit(1)
                )
                result = await session.execute(stmt)
                ai_msg = result.scalar_one_or_none()
                if not ai_msg or not ai_msg.tool_calls:
                    return {}
                from app.core.engine.message.utils import normalize_tool_calls
                tool_calls = normalize_tool_calls(ai_msg.tool_calls)
                
                for tc in tool_calls:
                    tc_id = tc.get("id")
                    if tc_id == tool_call_id:
                        args = tc.get("args", {})
                        return args or {}
        except Exception as e:
            logger.error(f"[MessageRepository] resolve_tool_input failed: {e}")
            raise
        return {}

    async def update_status_by_tool_call_id(self, tool_call_id: str, status: str) -> bool:
        """
        Update message status by tool_call_id (primarily for HITL closure).
        """
        try:
            async with session_scope() as session:
                from sqlalchemy import update
                stmt = (
                    update(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.tool_call_id == tool_call_id)
                    .values(status=status)
                )
                result = await session.execute(stmt)
                # No flush needed here as update() returns rowcount directly in some dialects, 
                # but session.execute with update statement is fine.
                logger.info(f"[MessageRepository] Updated status to {status} for tool_call_id {tool_call_id}")
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[MessageRepository] Failed to update status by tool_call_id {tool_call_id}: {e}")
            raise

    async def get_last_message_id(self) -> str | None:
        """Get the ID of the most recent message in the thread."""
        try:
            async with session_scope() as session:
                stmt = (
                    select(Message.id)
                    .where(Message.thread_id == self.thread_id)
                    .order_by(desc(Message.sequence_number))
                    .limit(1)
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[MessageRepository] Failed to get last message id: {e}")
            return None

    async def get_full_history(self, limit: int = 50, before_id: str | None = None) -> tuple[list[Message], bool, int | None]:
        """
        Fetches full conversation history including visible and associated invisible messages.
        Returns (messages, has_more, total_count).
        """
        async with session_scope() as session:
            # 1. Query visible messages with cursor pagination
            visible_stmt = (
                select(Message)
                .where(Message.thread_id == self.thread_id, Message.is_visible == True)
                .options(selectinload(Message.references))
                .order_by(Message.sequence_number.desc())
                .limit(limit + 1)
            )

            if before_id:
                before_seq = (await session.execute(
                    select(Message.sequence_number).where(Message.id == before_id)
                )).scalar_one_or_none()
                if before_seq:
                    visible_stmt = visible_stmt.where(Message.sequence_number < before_seq)

            result = await session.execute(visible_stmt)
            visible_messages = result.scalars().all()

            has_more = len(visible_messages) > limit
            if has_more:
                visible_messages = visible_messages[:limit]

            # 2. Fetch associated invisible messages for these runs
            run_ids = {m.run_id for m in visible_messages if m.run_id}
            
            # Special case: include current active run even if its messages are invisible
            if not before_id:
                latest_run_id = (await session.execute(
                    select(Message.run_id)
                    .where(Message.thread_id == self.thread_id, Message.run_id.is_not(None))
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if latest_run_id:
                    run_ids.add(latest_run_id)

            all_messages = list(visible_messages)
            if run_ids:
                invisible_stmt = (
                    select(Message)
                    .where(Message.thread_id == self.thread_id, Message.is_visible == False, Message.run_id.in_(run_ids))
                    .options(selectinload(Message.references))
                )
                invisible_messages = (await session.execute(invisible_stmt)).scalars().all()
                all_messages.extend(invisible_messages)

            all_messages.sort(key=lambda m: m.sequence_number or 0)

            # 3. Total count for first load
            total_count = None
            if not before_id:
                total_count = (await session.execute(
                    select(func.count(Message.id)).where(Message.thread_id == self.thread_id, Message.is_visible == True)
                )).scalar()

            return all_messages, has_more, total_count
