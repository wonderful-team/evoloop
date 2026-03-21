"""PostgreSQL implementation of short-term memory using Message table."""

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
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
        Retrieve recent messages for a thread, ordered by sequence_number.
        
        Args:
            thread_id: The conversation thread identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of LangChain messages in chronological order
        """
        async with session_scope() as db:
            stmt = select(Message).where(
                Message.thread_id == thread_id,
                Message.action_type.in_(["text", "thinking"]),  # Exclude tool_output for cleaner context
            ).order_by(Message.sequence_number.desc()).limit(limit)

            result = await db.execute(stmt)
            db_messages = result.scalars().all()

        # Convert to LangChain messages (reverse to get chronological order)
        lc_messages: list[BaseMessage] = []
        for msg in reversed(db_messages):
            if msg.role == "human":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "ai":
                lc_messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
            # Skip unknown roles

        logger.debug(f"SqlShortTermMemory: Retrieved {len(lc_messages)} messages for thread {thread_id}")
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
            
            # Focus on text and thinking for cleaner results
            stmt = stmt.where(Message.action_type.in_(["text", "thinking"]))
            stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
            
            result = await db.execute(stmt)
            db_messages = result.scalars().all()

        lc_messages: list[BaseMessage] = []
        for msg in db_messages:
            if msg.role == "human":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "ai":
                lc_messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
        
        return lc_messages
