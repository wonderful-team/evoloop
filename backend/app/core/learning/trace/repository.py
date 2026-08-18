"""TraceRepository — single point of DB access to ``trace_events``.

Recorder/mirroring flows (agent callback handler, Android mirror session,
recorder API routes, macro creator) funnel their ``trace_events`` reads and
writes through here instead of ad-hoc SQLAlchemy statements scattered across
callers.

Methods accept an optional ``db`` session so a caller that already holds a
transaction can keep it; otherwise each method opens its own
``session_scope()``. ``build_event`` is the single construction site for the
recorder/mirroring row shape (replaces the per-route builders).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import session_scope
from app.models.learning import TraceEvent

logger = logging.getLogger(__name__)


class TraceRepository:
    """Read/write access to the trace events table."""

    @staticmethod
    def build_event(
        *,
        member_id: int,
        session_id: str,
        thread_id: str | None,
        step_number: int,
        node_name: str,
        action_type: str,
        timestamp: int | float,
        event_type: str,
        source: str,
        app_name: str | None,
        payload: dict,
        state_context: dict,
        target_selector: str | None = None,
        target_text: str | None = None,
        mouse_x: float | None = None,
        mouse_y: float | None = None,
        window_title: str | None = None,
        action_payload: dict | None = None,
        is_human_action: bool = True,
    ) -> TraceEvent:
        """Single construction site for recorder/mirroring TraceEvent rows.

        ``action_payload`` defaults to the event payload itself (serialized).
        All recorder endpoints persist the same shape; only the payload
        contents and context tag differ.
        """
        return TraceEvent(
            member_id=member_id,
            session_id=session_id,
            recording_session_id=session_id,
            thread_id=thread_id,
            step_number=step_number,
            node_name=node_name,
            action_type=action_type,
            timestamp=timestamp,
            event_type=event_type,
            target_selector=target_selector,
            target_text=target_text,
            payload=payload,
            mouse_x=mouse_x,
            mouse_y=mouse_y,
            window_title=window_title,
            source=source,
            app_name=app_name,
            state_snapshot=state_context,
            action_payload=json.dumps(
                action_payload if action_payload is not None else payload
            ),
            is_human_action=is_human_action,
        )

    @staticmethod
    async def add(db: AsyncSession, event: TraceEvent) -> TraceEvent:
        """Persist a single trace event within the caller's session."""
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def add_all(db: AsyncSession, events: list[TraceEvent]) -> None:
        """Persist a batch of trace events within the caller's session."""
        if not events:
            return
        db.add_all(events)
        await db.flush()

    @staticmethod
    async def _query_all(
        stmt: Any,
        db: AsyncSession | None = None,
    ) -> list[TraceEvent]:
        async def _run(session: AsyncSession) -> list[TraceEvent]:
            return list((await session.execute(stmt)).scalars().all())

        if db is not None:
            return await _run(db)
        async with session_scope() as session:
            return await _run(session)

    @staticmethod
    async def count_by_session(
        session_id: str,
        member_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """Count trace events for a recording session (optionally member-scoped)."""
        stmt = select(func.count(TraceEvent.id)).where(
            TraceEvent.recording_session_id == session_id
        )
        if member_id is not None:
            stmt = stmt.where(TraceEvent.member_id == member_id)

        async def _run(session: AsyncSession) -> int:
            return (await session.execute(stmt)).scalar() or 0

        if db is not None:
            return await _run(db)
        async with session_scope() as session:
            return await _run(session)

    @staticmethod
    async def count_by_sessions(
        session_ids: list[str],
        db: AsyncSession | None = None,
    ) -> dict[str, int]:
        """Per-session event counts for a set of recording session ids."""
        if not session_ids:
            return {}

        async def _run(session: AsyncSession) -> dict[str, int]:
            stmt = (
                select(
                    TraceEvent.recording_session_id, func.count(TraceEvent.id)
                )
                .where(TraceEvent.recording_session_id.in_(session_ids))
                .group_by(TraceEvent.recording_session_id)
            )
            rows = (await session.execute(stmt)).all()
            return {sid: count for sid, count in rows if sid}

        if db is not None:
            return await _run(db)
        async with session_scope() as session:
            return await _run(session)

    @staticmethod
    async def get_by_session(
        session_id: str,
        member_id: int | None = None,
        action_type: str | None = None,
        match_session_id: bool = False,
        db: AsyncSession | None = None,
    ) -> list[TraceEvent]:
        """Fetch trace events for a recording session, ordered by timestamp.

        Optionally scoped to a member and/or a specific ``action_type``. When
        ``match_session_id`` is set, rows matching either ``session_id`` or
        ``recording_session_id`` are returned.
        """
        condition = (
            or_(
                TraceEvent.session_id == session_id,
                TraceEvent.recording_session_id == session_id,
            )
            if match_session_id
            else TraceEvent.recording_session_id == session_id
        )
        stmt = select(TraceEvent).where(condition)
        if member_id is not None:
            stmt = stmt.where(TraceEvent.member_id == member_id)
        if action_type is not None:
            stmt = stmt.where(TraceEvent.action_type == action_type)
        stmt = stmt.order_by(TraceEvent.timestamp)
        return await TraceRepository._query_all(stmt, db=db)

    @staticmethod
    async def get_by_thread(
        thread_id: str,
        db: AsyncSession | None = None,
    ) -> list[TraceEvent]:
        """Fetch all trace events for a thread, ordered by step number."""
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.thread_id == thread_id)
            .order_by(TraceEvent.step_number)
        )
        return await TraceRepository._query_all(stmt, db=db)

    @staticmethod
    async def delete_by_session(
        session_id: str,
        member_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """Delete trace events for a recording session (optionally member-scoped).

        Matches rows by either ``recording_session_id`` or ``session_id``.
        Returns the number of deleted rows.
        """
        stmt = delete(TraceEvent).where(
            or_(
                TraceEvent.recording_session_id == session_id,
                TraceEvent.session_id == session_id,
            )
        )
        if member_id is not None:
            stmt = stmt.where(TraceEvent.member_id == member_id)

        async def _run(session: AsyncSession) -> int:
            result = await session.execute(stmt)
            return result.rowcount or 0

        if db is not None:
            return await _run(db)
        async with session_scope() as session:
            return await _run(session)

    @staticmethod
    async def delete_by_thread(
        thread_id: str,
        message_ids: list[str] | None = None,
        run_ids: list[str] | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """Delete trace events for a thread, optionally narrowed by message/run ids.

        Returns the number of deleted rows. With no id filters the whole
        thread's events are removed.
        """
        stmt = delete(TraceEvent).where(TraceEvent.thread_id == thread_id)
        conditions: list[Any] = []
        if message_ids:
            conditions.append(TraceEvent.message_id.in_(message_ids))
        if run_ids:
            conditions.append(TraceEvent.run_id.in_(run_ids))

        if len(conditions) > 1:
            stmt = stmt.where(or_(*conditions))
        elif conditions:
            stmt = stmt.where(conditions[0])

        async def _run(session: AsyncSession) -> int:
            result = await session.execute(stmt)
            return result.rowcount or 0

        if db is not None:
            return await _run(db)
        async with session_scope() as session:
            return await _run(session)


trace_repository = TraceRepository()
