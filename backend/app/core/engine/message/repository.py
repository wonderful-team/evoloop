"""
MessageRepository — Database persistence and query operations for messages.

Extracted from MessageHandler to separate persistence concerns from orchestration.
"""

import json
import logging
from typing import Any

from sqlalchemy import desc, select

from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.core.engine.message.sequence import SequenceService

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
    ) -> tuple[str | None, int]:
        """
        Persist a message to the database.

        Returns:
            (message_id, sequence_number) or (None, 0) on failure
        """
        if not content and not thinking and not tool_calls:
            logger.warning(f"[MessageRepository] Skipping persist for {role}: no content, thinking, or tool_calls")
            return None, 0

        try:
            seq = await SequenceService.next_sequence(self.thread_id)
            logger.info(f"[MessageRepository] Persisting {role} message (seq={seq}, cat={category})")

            async with session_scope() as session:
                log = Message(
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
                )
                session.add(log)
                await session.flush()

            msg_id = f"msg-{self.thread_id}-{seq}"
            return msg_id, seq

        except Exception as e:
            logger.error(f"[MessageRepository] Failed to persist message: {e}")
            return None, 0

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
                tool_calls = ai_msg.tool_calls
                if isinstance(tool_calls, str):
                    try:
                        tool_calls = json.loads(tool_calls)
                    except Exception:
                        return {}
                for tc in (tool_calls or []):
                    tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    if tc_id == tool_call_id:
                        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                        return args or {}
        except Exception as e:
            logger.debug(f"[MessageRepository] resolve_tool_input failed: {e}")
        return {}
