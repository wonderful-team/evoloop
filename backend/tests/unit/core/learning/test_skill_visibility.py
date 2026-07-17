"""Matrix tests for the single skill visibility/routability gate.

Pins the (status, is_active) -> visible/routable mapping so every reader
(route index gate, list endpoint, hydrator, discovery, tools, wiki) agrees,
and proves the SQL filter and the Python predicates select the same rows on
a real database.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.learning import skill_visibility
from app.core.learning.skill_visibility import (
    is_routable,
    is_visible,
    visible_filter,
)
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill


def _skill(status, is_active=True):
    return SimpleNamespace(status=status, is_active=is_active)


def _set_require_verified(monkeypatch, value: bool):
    monkeypatch.setattr(
        skill_visibility.settings, "ROUTE_INDEX_REQUIRE_VERIFIED", value
    )


class TestVisible:
    def test_active_is_visible(self):
        assert is_visible(_skill("verified", True)) is True

    def test_inactive_is_hidden(self):
        assert is_visible(_skill("verified", False)) is False

    def test_none_is_active_stays_visible(self):
        # Legacy: only an explicit False hides a row.
        assert is_visible(_skill("verified", None)) is True


class TestRoutableVerifiedMode:
    @pytest.mark.parametrize(
        ("status", "is_active", "expected"),
        [
            ("verified", True, True),
            ("verified", False, False),
            ("active", True, False),  # P3: tightened; legacy rows repaired by migration
            ("active", False, False),
            ("pending_review", True, False),
            ("pending_review", False, False),
            ("draft", True, False),
            ("candidate", True, False),
            ("needs_update", True, False),
            ("deprecated", True, False),
            ("archived", True, False),
            (None, True, False),
        ],
    )
    def test_matrix(self, monkeypatch, status, is_active, expected):
        _set_require_verified(monkeypatch, True)
        assert is_routable(_skill(status, is_active)) is expected


class TestRoutableLegacyMode:
    @pytest.mark.parametrize(
        ("status", "is_active", "expected"),
        [
            ("verified", True, True),
            ("pending_review", True, True),
            ("draft", True, True),
            ("active", True, True),  # legacy mode only blocks retired statuses
            (None, True, True),
            ("archived", True, False),
            ("disabled", True, False),
            ("inactive", True, False),
            ("verified", False, False),
            ("archived", False, False),
        ],
    )
    def test_matrix(self, monkeypatch, status, is_active, expected):
        _set_require_verified(monkeypatch, False)
        assert is_routable(_skill(status, is_active)) is expected


async def _insert_skill(**kwargs) -> int:
    async with session_scope() as db:
        kwargs.setdefault("name", "s")
        kwargs.setdefault("description", "")
        kwargs.setdefault("trigger_patterns", "[]")
        kwargs.setdefault("parameters", "[]")
        skill = LearnedSkill(**kwargs)
        db.add(skill)
        await db.flush()
        return skill.id


@pytest.mark.asyncio
async def test_sql_filter_agrees_with_python_predicates(_real_db, monkeypatch):
    """visible_filter (SQL), is_visible and is_routable must agree on real rows:
    the visible set is exactly is_active=True rows, and the routable set is the
    visible rows whose status is trusted."""
    _set_require_verified(monkeypatch, True)
    ids = {}
    for key, status, active in [
        ("verified_active", "verified", True),
        ("verified_inactive", "verified", False),
        ("pending_active", "pending_review", True),
    ]:
        ids[key] = await _insert_skill(name=key, status=status, is_active=active)

    async with session_scope() as db:
        visible_rows = (
            (await db.execute(select(LearnedSkill).where(visible_filter())))
            .scalars()
            .all()
        )
        all_rows = (await db.execute(select(LearnedSkill))).scalars().all()

    visible_ids = {s.id for s in visible_rows}
    assert visible_ids == {ids["verified_active"], ids["pending_active"]}
    assert {s.id for s in all_rows if is_visible(s)} == visible_ids
    assert {s.id for s in all_rows if is_routable(s)} == {ids["verified_active"]}
