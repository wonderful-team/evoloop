"""
SequenceService — Atomic thread-local sequence number generation.

Replaces the race-prone SELECT MAX(sequence_number) + 1 pattern
with a database-native atomic counter.
"""

import logging

from sqlalchemy import text

from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)


class SequenceService:
    """
    Generate unique sequence numbers per thread.

    Uses INSERT ... ON CONFLICT DO UPDATE for atomicity.
    Works with both SQLite and PostgreSQL.
    """

    @staticmethod
    async def next_sequence(thread_id: str, session=None) -> int:
        """
        Atomically get the next sequence number for a thread.

        Args:
            thread_id: The conversation thread ID
            session: Optional shared AsyncSession. If not provided, creates a new one.

        Returns:
            The next sequence number (starting from 1)
        """
        if session is None:
            async with session_scope() as s:
                return await SequenceService._next_sequence(thread_id, s)
        return await SequenceService._next_sequence(thread_id, session)

    @staticmethod
    async def _next_sequence(thread_id: str, session) -> int:
        stmt = text(
            """
            INSERT INTO thread_sequences (thread_id, next_seq)
            VALUES (:thread_id, 2)
            ON CONFLICT (thread_id) DO UPDATE
            SET next_seq = thread_sequences.next_seq + 1
            RETURNING next_seq - 1
            """
        )
        result = await session.execute(stmt, {"thread_id": thread_id})
        seq = result.scalar()
        if seq is None:
            from sqlalchemy import select

            from app.models import ThreadSequence

            row = await session.execute(
                select(ThreadSequence.next_seq).where(ThreadSequence.thread_id == thread_id)
            )
            seq = row.scalar() or 1

        return seq

    @staticmethod
    async def set_sequence(thread_id: str, next_seq: int) -> None:
        """
        Manually set the next sequence number for a thread.
        Used during rewind/reset operations to maintain continuity.
        """
        async with session_scope() as session:
            stmt = text(
                """
                INSERT INTO thread_sequences (thread_id, next_seq)
                VALUES (:thread_id, :next_seq)
                ON CONFLICT (thread_id) DO UPDATE
                SET next_seq = :next_seq
                """
            )
            await session.execute(stmt, {"thread_id": thread_id, "next_seq": next_seq})
            logger.info(f"[SequenceService] Manually set next_seq for {thread_id} to {next_seq}")
