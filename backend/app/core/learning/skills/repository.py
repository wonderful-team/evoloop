"""SkillRepository — single point of DB access to ``learned_skills``.

Reads that need membership scoping or non-visible rows (CRUD routes,
wiki/profile bootstrap, scheduler, engine signals) funnel through here
instead of ad-hoc ``select(LearnedSkill)`` calls scattered across callers.

Conventions:
- ``member_id=None`` → no member scoping (global rows only).
- ``member_id=<id>`` → rows owned by ``0`` (system) or ``<id>``.
- ``visible_only=True`` → apply :func:`app.core.learning.skills.visibility.visible_filter`.

Read methods accept an optional ``db`` session so a caller that already
holds a transaction (e.g. the validate route that mutates the returned
object) can keep the row attached; otherwise each method opens its own
``session_scope()``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.learning.skills.visibility import visible_filter
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


def _scope(member_id: int | None, include_system: bool = True) -> Any | None:
    """Return the membership-scope SQL condition (None when unscoped).

    ``member_id=None`` → no scoping. With ``include_system=True`` rows owned
    by ``0`` (system) or ``member_id`` match; with ``False`` only the
    caller-owned rows match (write flows).
    """
    if member_id is None:
        return None
    if include_system:
        return or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == member_id)
    return LearnedSkill.member_id == member_id


class SkillRepository:
    """Read-only access to the learned skills table."""

    @staticmethod
    async def _fetch_one(
        *where: Any,
        member_id: int | None = None,
        visible_only: bool = False,
        include_system: bool = True,
        db: AsyncSession | None = None,
    ) -> LearnedSkill | None:
        async def _query(session: AsyncSession) -> LearnedSkill | None:
            stmt = select(LearnedSkill).where(*where)
            scope = _scope(member_id, include_system=include_system)
            if scope is not None:
                stmt = stmt.where(scope)
            if visible_only:
                stmt = stmt.where(visible_filter())
            return (await session.execute(stmt)).scalar_one_or_none()

        if db is not None:
            return await _query(db)
        async with session_scope() as session:
            return await _query(session)

    @staticmethod
    async def get_by_id(
        skill_id: int,
        member_id: int | None = None,
        visible_only: bool = False,
        include_system: bool = True,
        db: AsyncSession | None = None,
    ) -> LearnedSkill | None:
        """Fetch a skill by primary key (with optional scope/visibility)."""
        if not skill_id:
            return None
        return await SkillRepository._fetch_one(
            LearnedSkill.id == skill_id,
            member_id=member_id,
            visible_only=visible_only,
            include_system=include_system,
            db=db,
        )

    @staticmethod
    async def get_by_name(
        name: str,
        member_id: int | None = None,
        visible_only: bool = False,
        include_system: bool = True,
        db: AsyncSession | None = None,
    ) -> LearnedSkill | None:
        """Fetch a skill by exact name (with optional scope/visibility)."""
        if not name:
            return None
        return await SkillRepository._fetch_one(
            LearnedSkill.name == name,
            member_id=member_id,
            visible_only=visible_only,
            include_system=include_system,
            db=db,
        )

    @staticmethod
    async def get_by_ids(
        skill_ids: list[int | str],
        visible_only: bool = False,
        db: AsyncSession | None = None,
    ) -> list[LearnedSkill]:
        """Batch-load skills by id list (optionally filtered to visible).

        Accepts string ids because agent-facing callers (e.g. engine signals)
        may pass raw tool-call arguments; the integer PK comparison is coerced
        by the database.
        """
        if not skill_ids:
            return []

        async def _query(session: AsyncSession) -> list[LearnedSkill]:
            stmt = select(LearnedSkill).where(LearnedSkill.id.in_(skill_ids))
            if visible_only:
                stmt = stmt.where(visible_filter())
            return list((await session.execute(stmt)).scalars().all())

        if db is not None:
            return await _query(db)
        async with session_scope() as session:
            return await _query(session)

    @staticmethod
    async def list_page(
        page: int,
        page_size: int,
        member_id: int | None = None,
        active_only: bool = True,
        db: AsyncSession | None = None,
    ) -> tuple[list[LearnedSkill], int]:
        """Paginated skill listing (with member scope and visibility).

        Returns ``(rows, total)`` ordered by ``created_at`` descending.
        """
        if page < 1:
            page = 1

        async def _query(session: AsyncSession) -> tuple[list[LearnedSkill], int]:
            base = select(LearnedSkill)
            scope = _scope(member_id)
            if scope is not None:
                base = base.where(scope)
            if active_only:
                base = base.where(visible_filter())

            count_stmt = select(func.count()).select_from(base.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            stmt = (
                base.order_by(LearnedSkill.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return rows, total

        if db is not None:
            return await _query(db)
        async with session_scope() as session:
            return await _query(session)

    @staticmethod
    async def validate_ids(
        skill_ids: list[int],
        db: AsyncSession | None = None,
    ) -> list[int]:
        """Return the subset of ``skill_ids`` that do not exist in the table."""
        if not skill_ids:
            return []

        async def _query(session: AsyncSession) -> list[int]:
            stmt = select(LearnedSkill.id).where(LearnedSkill.id.in_(skill_ids))
            existing = set((await session.execute(stmt)).scalars().all())
            return sorted(set(skill_ids) - existing)

        if db is not None:
            return await _query(db)
        async with session_scope() as session:
            return await _query(session)


skill_repository = SkillRepository()
