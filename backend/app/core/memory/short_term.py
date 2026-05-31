"""PostgreSQL implementation of short-term memory using Message table."""
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy import delete, or_, select

from app.core.memory.interfaces.short_term import IShortTermMemory
from app.infrastructure.database.sql.database import session_scope
from app.models.conversation import Message

logger = logging.getLogger(__name__)


class SqlShortTermMemory(IShortTermMemory):
    """
    PostgreSQL implementation of short-term memory.
    Uses the existing Message table to store and retrieve conversation context.
    """

    async def initialize(self) -> None:
        logger.info("SqlShortTermMemory: Initialized (using existing Message table)")

    async def flush(self) -> None:
        async with session_scope() as db:
            await db.execute(delete(Message))
            await db.commit()
        logger.warning("SqlShortTermMemory: Flushed all messages (testing mode)")

    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        if isinstance(message, HumanMessage):
            role = "human"
        elif isinstance(message, AIMessage):
            role = "ai"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            role = "unknown"

        async with session_scope() as db:
            stmt = select(Message.sequence_number).where(
                Message.thread_id == thread_id
            ).order_by(Message.sequence_number.desc()).limit(1)
            result = await db.execute(stmt)
            last_seq = result.scalar()
            next_seq = (last_seq or 0) + 1

            import uuid
            new_message = Message(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                role=role,
                content=message.content if isinstance(message.content, str) else str(message.content),
                sequence_number=next_seq,
                action_type="text",
            )
            db.add(new_message)
            await db.commit()

        logger.debug(f"SqlShortTermMemory: Added {role} message to thread {thread_id}")

    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        async with session_scope() as db:
            visible_stmt = select(Message).where(
                Message.thread_id == thread_id,
                Message.is_visible == True,
            ).order_by(Message.id.desc()).limit(limit)

            result = await db.execute(visible_stmt)
            visible_messages = result.scalars().all()
            visible_messages = list(reversed(visible_messages))

            recent_run_ids = set()
            ai_count = 0
            for msg in reversed(visible_messages):
                if msg.role == "ai" and msg.run_id:
                    recent_run_ids.add(msg.run_id)
                    ai_count += 1
                    if ai_count >= 2:
                        break

            latest_run_stmt = select(Message.run_id).where(
                Message.thread_id == thread_id, Message.run_id.is_not(None)
            ).order_by(Message.id.desc()).limit(1)
            latest_run_id = (await db.execute(latest_run_stmt)).scalar_one_or_none()
            if latest_run_id:
                recent_run_ids.add(latest_run_id)

            invisible_messages = []
            if recent_run_ids:
                invisible_stmt = select(Message).where(
                    Message.thread_id == thread_id,
                    Message.is_visible == False,
                    Message.run_id.in_(recent_run_ids)
                ).order_by(Message.sequence_number.asc())

                invisible_result = await db.execute(invisible_stmt)
                invisible_messages = invisible_result.scalars().all()

            all_messages = visible_messages + list(invisible_messages)
            all_messages.sort(key=lambda m: m.id)

        lc_messages: list[BaseMessage] = []
        pending_tool_calls: dict[int, list[dict]] = {}

        for msg in all_messages:
            if msg.role == "human":
                lc_messages.append(HumanMessage(content=msg.content or ""))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content or ""))
            elif msg.role == "ai":
                kwargs = {"content": msg.content or ""}
                if msg.tool_calls:
                    kwargs["tool_calls"] = msg.tool_calls
                    pending_tool_calls[msg.id] = list(msg.tool_calls)
                thinking_raw = msg.thinking
                if thinking_raw:
                    kwargs["additional_kwargs"] = {"thinking": thinking_raw}
                lc_messages.append(AIMessage(**kwargs))
            elif msg.role == "tool":
                parent_calls = pending_tool_calls.get(msg.parent_id, [])
                if parent_calls:
                    tc = parent_calls.pop(0)
                    tool_call_id = tc.get("id", f"orphan_{msg.id}")
                    name = tc.get("name", "unknown")
                else:
                    tool_call_id = f"orphan_{msg.id}"
                    name = "unknown"

                lc_messages.append(ToolMessage(
                    content=msg.content or "",
                    tool_call_id=tool_call_id,
                    name=name
                ))

        logger.debug(f"SqlShortTermMemory: Retrieved {len(lc_messages)} messages for thread {thread_id}")
        return lc_messages

    async def prune(self, thread_id: str) -> None:
        MAX_MESSAGES = 100

        async with session_scope() as db:
            count_stmt = select(Message).where(Message.thread_id == thread_id)
            result = await db.execute(count_stmt)
            all_messages = result.scalars().all()
            total_count = len(all_messages)

            if total_count <= MAX_MESSAGES:
                return

            to_delete = total_count - MAX_MESSAGES
            oldest_stmt = select(Message.id).where(
                Message.thread_id == thread_id
            ).order_by(Message.sequence_number.asc()).limit(to_delete)

            result = await db.execute(oldest_stmt)
            ids_to_delete = [r for r in result.scalars().all()]

            if ids_to_delete:
                delete_stmt = delete(Message).where(Message.id.in_(ids_to_delete))
                await db.execute(delete_stmt)
                await db.commit()
                logger.info(f"SqlShortTermMemory: Pruned {len(ids_to_delete)} old messages from thread {thread_id}")

    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10) -> list[BaseMessage]:
        async with session_scope() as db:
            keywords = [k.strip() for k in query.split() if k.strip()]

            if len(keywords) == 1:
                stmt = select(Message).where(Message.content.ilike(f"%{keywords[0]}%"))
            elif len(keywords) > 1:
                conditions = [Message.content.ilike(f"%{k}%") for k in keywords]
                stmt = select(Message).where(or_(*conditions))
            else:
                return []

            if thread_id:
                stmt = stmt.where(Message.thread_id == thread_id)

            stmt = stmt.where(Message.is_visible == True)
            stmt = stmt.order_by(Message.created_at.desc()).limit(limit)

            result = await db.execute(stmt)
            db_messages = result.scalars().all()

        lc_messages: list[BaseMessage] = []
        for msg in db_messages:
            if msg.role == "human":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "ai":
                kwargs = {"content": msg.content}
                thinking_raw = msg.thinking
                if thinking_raw:
                    kwargs["additional_kwargs"] = {"thinking": thinking_raw}
                lc_messages.append(AIMessage(**kwargs))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))

        return lc_messages
