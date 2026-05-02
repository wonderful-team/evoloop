"""PostgreSQL implementation of short-term memory using Message table."""
import json
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
    This is a lightweight adapter that bridges the IShortTermMemory interface
    with the existing message storage infrastructure.
    """

    async def initialize(self) -> None:
        """
        No-op: Message table is managed by Alembic migrations.
        """
        logger.info("SqlShortTermMemory: Initialized (using existing Message table)")

    async def flush(self) -> None:
        """
        Clear all messages (for testing only).
        
        WARNING: This will delete ALL messages in the database.
        """
        async with session_scope() as db:
            await db.execute(delete(Message))
            await db.commit()
        logger.warning("SqlShortTermMemory: Flushed all messages (testing mode)")

    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """
        Insert a message into the Message table.
        
        Args:
            thread_id: The conversation thread identifier
            message: The LangChain message to store
        """
        # Determine role from message type
        if isinstance(message, HumanMessage):
            role = "human"
        elif isinstance(message, AIMessage):
            role = "ai"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            role = "unknown"

        # Get next sequence number
        async with session_scope() as db:
            # Get max sequence number for this thread
            stmt = select(Message.sequence_number).where(
                Message.thread_id == thread_id
            ).order_by(Message.sequence_number.desc()).limit(1)
            result = await db.execute(stmt)
            last_seq = result.scalar()
            next_seq = (last_seq or 0) + 1

            # Create new message
            new_message = Message(
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
        """
        Retrieve context with a Hybrid Compaction strategy:
        - Last N visible conversation turns (Human/AI text) are loaded.
        - Only for the VERY RECENT (last 2) turns do we load the granular Tool records.
        - Maps ToolMessages strictly to their AI tool_calls to satisfy OpenAI/Langchain requirements.
        """
        async with session_scope() as db:
            # 1. Fetch the visible "backbone" messages
            visible_stmt = select(Message).where(
                Message.thread_id == thread_id,
                Message.is_visible == True,
            ).order_by(Message.id.desc()).limit(limit)

            result = await db.execute(visible_stmt)
            visible_messages = result.scalars().all()

            # Reverse to temporal order
            visible_messages = list(reversed(visible_messages))

            # 2. Identify the run_ids of the LAST 2 visible AI elements
            # This represents the "recent" active context where we want full granular tool fidelity
            recent_run_ids = set()
            ai_count = 0
            for msg in reversed(visible_messages):
                if msg.role == "ai" and msg.run_id:
                    recent_run_ids.add(msg.run_id)
                    ai_count += 1
                    if ai_count >= 2:
                        break

            # Fallback: catch the absolute latest active run_id in case it hasn't produced a visible msg yet
            latest_run_stmt = select(Message.run_id).where(
                Message.thread_id == thread_id, Message.run_id.is_not(None)
            ).order_by(Message.id.desc()).limit(1)
            latest_run_id = (await db.execute(latest_run_stmt)).scalar_one_or_none()
            if latest_run_id:
                recent_run_ids.add(latest_run_id)

            # 3. Fetch all invisible (tool calls/results) ONLY for those recent run_ids
            invisible_messages = []
            if recent_run_ids:
                invisible_stmt = select(Message).where(
                    Message.thread_id == thread_id,
                    Message.is_visible == False,
                    Message.run_id.in_(recent_run_ids)
                ).order_by(Message.id.asc())

                invisible_result = await db.execute(invisible_stmt)
                invisible_messages = invisible_result.scalars().all()

            # Merge all components and sort chronologically by ID
            all_messages = visible_messages + list(invisible_messages)
            all_messages.sort(key=lambda m: m.id)

        # 4. Convert to strict LangChain Messages
        lc_messages: list[BaseMessage] = []
        pending_tool_calls: dict[int, list[dict]] = {}  # Keeps track of open tool calls per parent AI message

        for msg in all_messages:
            if msg.role == "human":
                lc_messages.append(HumanMessage(content=msg.content or ""))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content or ""))
            elif msg.role == "ai":
                kwargs = {"content": msg.content or ""}
                if msg.tool_calls:
                    kwargs["tool_calls"] = msg.tool_calls
                    # Stash them so ToolMessages can claim their IDs
                    pending_tool_calls[msg.id] = list(msg.tool_calls)
                # Preserve thinking content in additional_kwargs for reasoning models
                thinking_raw = msg.thinking
                if thinking_raw:
                    kwargs["additional_kwargs"] = {"thinking": thinking_raw}
                lc_messages.append(AIMessage(**kwargs))
            elif msg.role == "tool":
                parent_calls = pending_tool_calls.get(msg.parent_id, [])
                if parent_calls:
                    # FIFO mapping for sequential tool calls
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

        logger.debug(f"SqlShortTermMemory: Retrieved {len(lc_messages)} messages (Hybrid Compressed) for thread {thread_id}")
        return lc_messages

    async def prune(self, thread_id: str) -> None:
        """
        Apply pruning strategy to reduce token pressure.
        
        Current implementation: Delete messages beyond a threshold (e.g., keep last 100).
        Future: Could use LLM to summarize older messages.
        
        Args:
            thread_id: The conversation thread to prune
        """
        MAX_MESSAGES = 100

        async with session_scope() as db:
            # Get total count
            count_stmt = select(Message).where(Message.thread_id == thread_id)
            result = await db.execute(count_stmt)
            all_messages = result.scalars().all()
            total_count = len(all_messages)

            if total_count <= MAX_MESSAGES:
                logger.debug(f"SqlShortTermMemory: No pruning needed for thread {thread_id} ({total_count} messages)")
                return

            # Get IDs of oldest messages to delete
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
        """
        Search for messages containing the query string using SQL LIKE.
        Supports multi-keyword search (space-separated keywords are OR-ed).
        """
        async with session_scope() as db:
            # Build multi-keyword search (space-separated = OR)
            keywords = [k.strip() for k in query.split() if k.strip()]

            if len(keywords) == 1:
                # Single keyword - simple LIKE
                stmt = select(Message).where(Message.content.ilike(f"%{keywords[0]}%"))
            elif len(keywords) > 1:
                # Multiple keywords - OR condition
                conditions = [Message.content.ilike(f"%{k}%") for k in keywords]
                stmt = select(Message).where(or_(*conditions))
            else:
                # Empty query - return nothing
                return []

            if thread_id:
                stmt = stmt.where(Message.thread_id == thread_id)

            # Focus on visible main conversation nodes for cleaner results
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
                # Preserve thinking content in additional_kwargs for reasoning models
                thinking_raw = msg.thinking
                if thinking_raw:
                    kwargs["additional_kwargs"] = {"thinking": thinking_raw}
                lc_messages.append(AIMessage(**kwargs))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))

        return lc_messages
