"""State-consistency regression tests for the macro lifecycle (audit P1/P2).

These tests run in-process against a throwaway SQLite DB and verify the
publish/state contract of the lifecycle DAOs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.learning.macro import lifecycle
from app.models.macro import Macro


def _build_macro(status: str, is_active: bool) -> Macro:
    return Macro(
        name="state-test",
        description="",
        trigger_patterns=[],
        parameters=[],
        macro_script="steps: []",
        status=status,
        is_active=is_active,
    )


@pytest.fixture
def lifecycle_scope(test_session_scope, monkeypatch):
    monkeypatch.setattr(lifecycle, "session_scope", test_session_scope)
    publish = AsyncMock()
    monkeypatch.setattr(lifecycle, "publish_macro_mutated", publish)
    return publish


@pytest.mark.asyncio
class TestConfirmMacroStateMachine:
    async def test_confirm_rejects_obsolete(
        self, test_session_scope, lifecycle_scope
    ) -> None:
        async with test_session_scope() as db:
            macro = _build_macro(status="obsolete", is_active=False)
            db.add(macro)
            await db.flush()
            macro_id = macro.id

        ok = await lifecycle.confirm_macro(macro_id)
        assert ok is False  # obsolete is a terminal state; must not be resurrected

        async with test_session_scope() as db:
            m = await db.get(Macro, macro_id)
            assert m.status == "obsolete"
            assert m.is_active is False
        lifecycle_scope.assert_not_awaited()

    async def test_confirm_verified_is_idempotent_no_event(
        self, test_session_scope, lifecycle_scope
    ) -> None:
        async with test_session_scope() as db:
            macro = _build_macro(status="verified", is_active=True)
            db.add(macro)
            await db.flush()
            macro_id = macro.id

        ok = await lifecycle.confirm_macro(macro_id)
        assert ok is True  # already verified: no-op, no duplicate event

        lifecycle_scope.assert_not_awaited()
        async with test_session_scope() as db:
            m = await db.get(Macro, macro_id)
            assert m.status == "verified"

    async def test_confirm_pending_review_promotes(
        self, test_session_scope, lifecycle_scope
    ) -> None:
        async with test_session_scope() as db:
            macro = _build_macro(status="pending_review", is_active=False)
            db.add(macro)
            await db.flush()
            macro_id = macro.id

        ok = await lifecycle.confirm_macro(macro_id)
        assert ok is True

        lifecycle_scope.assert_awaited_once_with(macro_id, action="update")
        async with test_session_scope() as db:
            m = await db.get(Macro, macro_id)
            assert m.status == "verified"
            assert m.is_active is True


@pytest.mark.asyncio
class TestConfirmBulkPublishContract:
    async def test_bulk_does_not_publish_unchanged_ids(
        self, test_session_scope, lifecycle_scope
    ) -> None:
        async with test_session_scope() as db:
            verified = _build_macro(status="verified", is_active=True)
            db.add(verified)
            await db.flush()
            verified_id = verified.id

        count = await lifecycle.confirm_bulk([verified_id, 999_999])
        assert count == 0  # nothing was promoted

        # No state changed -> no lifecycle event for either id.
        lifecycle_scope.assert_not_awaited()

    async def test_bulk_publishes_only_promoted(
        self, test_session_scope, lifecycle_scope
    ) -> None:
        async with test_session_scope() as db:
            pending = _build_macro(status="pending_review", is_active=False)
            db.add(pending)
            await db.flush()
            pending_id = pending.id

            verified = _build_macro(status="verified", is_active=True)
            db.add(verified)
            await db.flush()
            verified_id = verified.id

        count = await lifecycle.confirm_bulk([pending_id, verified_id])
        assert count == 1

        # Only the pending one (which actually changed) publishes an event.
        lifecycle_scope.assert_awaited_once_with(pending_id, action="update")
