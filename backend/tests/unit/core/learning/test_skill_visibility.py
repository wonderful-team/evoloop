"""Unit coverage for skill visibility/routability predicates."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.learning.skills.visibility import (
    ROUTABLE_STATUSES,
    is_routable,
    is_visible,
    visible_filter,
)


def _skill(**kw) -> SimpleNamespace:
    defaults = {"is_active": True, "status": "verified"}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestIsVisible:
    def test_active(self):
        assert is_visible(_skill(is_active=True)) is True

    def test_inactive(self):
        assert is_visible(_skill(is_active=False)) is False

    def test_none_defaults_visible(self):
        # getattr fallback: missing is_active is treated as visible
        assert is_visible(SimpleNamespace()) is True

    def test_none_is_active_visible(self):
        assert is_visible(_skill(is_active=None)) is True


class TestIsRoutable:
    def test_verified_is_routable(self):
        assert is_routable(_skill(status="verified")) is True

    def test_inactive_never_routable(self):
        assert is_routable(_skill(status="verified", is_active=False)) is False

    def test_pending_review_not_routable(self):
        assert is_routable(_skill(status="pending_review")) is False

    def test_candidate_not_routable(self):
        assert is_routable(_skill(status="candidate")) is False

    def test_missing_status_not_routable(self):
        assert is_routable(_skill(status=None)) is False

    def test_archived_blocked(self):
        assert is_routable(_skill(status="archived")) is False

    def test_verified_is_in_routeable_set(self):
        assert "verified" in ROUTABLE_STATUSES


class TestVisibleFilter:
    def test_returns_sql_expression(self):
        # visible_filter should compile to an is_active == true predicate
        expr = visible_filter()
        assert expr is not None
