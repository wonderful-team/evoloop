"""Single source of truth for LearnedSkill visibility and routability.

Every reader of LearnedSkill must funnel through these predicates (or the
matching SQL filter) so the lifecycle gate exists exactly once:

- ``is_visible``: may appear in lists / agent context (the historical
  ``is_active == True`` SQL filter).
- ``is_routable``: may enter the route index and be auto-executed.

Preserved legacy asymmetry: ``is_visible`` on an in-memory row treats a NULL
``is_active`` as visible (only an explicit False hides it), while
``visible_filter`` (SQL) excludes NULL. The column is non-nullable with
default True, so NULL only exists in corrupt legacy data.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.learning.constants import ROUTABLE_STATUSES
from app.models.learning import LearnedSkill

# Statuses excluded even in legacy permissive mode
# (ROUTE_INDEX_REQUIRE_VERIFIED off): only explicitly retired rows skip.
_LEGACY_BLOCKED_STATUSES = frozenset({"archived", "disabled", "inactive"})


def is_visible(skill: Any) -> bool:
    """Whether a skill may appear in lists / agent context."""
    return getattr(skill, "is_active", True) is not False


def is_routable(skill: Any) -> bool:
    """Whether a skill may enter the route index (auto execution)."""
    if not is_visible(skill):
        return False
    status = getattr(skill, "status", None)
    if not settings.ROUTE_INDEX_REQUIRE_VERIFIED:
        # Legacy permissive mode: only explicitly retired rows skip.
        if status and str(status).lower() in _LEGACY_BLOCKED_STATUSES:
            return False
        return True
    if status is None:
        return False
    return str(status).lower() in ROUTABLE_STATUSES


def visible_filter() -> Any:
    """SQLAlchemy condition equivalent of is_visible for select() statements."""
    return LearnedSkill.is_active.is_(True)
