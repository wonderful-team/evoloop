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


class TestProjectSkillScoping:
    def test_capability_index_filters_foreign_project_skills(self):
        from app.core.engine.react.prompts import _capability_index

        global_skill = SimpleNamespace(
            name="agent-reach",
            display_name="Agent Reach",
            description="Global web search and scrape",
            project_id=None,
        )
        project_skill = SimpleNamespace(
            name="order-refund",
            display_name="Refund Handler",
            description="Member center refund",
            project_id=120,
        )
        foreign_skill = SimpleNamespace(
            name="mall-marketing",
            display_name="Mall Marketing",
            description="Marketing tools",
            project_id=999,
        )

        # Context for project 120
        ctx_120 = SimpleNamespace(
            project_id=120,
            metadata={
                "active_skills": [global_skill, project_skill, foreign_skill],
            },
        )
        idx_120 = _capability_index(ctx_120)
        assert "agent-reach" in idx_120
        assert "order-refund" in idx_120
        assert "mall-marketing" not in idx_120

        # Context for project 122 (different project)
        ctx_122 = SimpleNamespace(
            project_id=122,
            metadata={
                "active_skills": [global_skill, project_skill, foreign_skill],
            },
        )
        idx_122 = _capability_index(ctx_122)
        assert "agent-reach" in idx_122
        assert "order-refund" not in idx_122
        assert "mall-marketing" not in idx_122

        # Context with no project_id (workspace global)
        ctx_none = SimpleNamespace(
            project_id=None,
            metadata={
                "active_skills": [global_skill, project_skill, foreign_skill],
            },
        )
        idx_none = _capability_index(ctx_none)
        assert "agent-reach" in idx_none
        assert "order-refund" not in idx_none
        assert "mall-marketing" not in idx_none

