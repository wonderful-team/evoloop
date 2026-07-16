"""One-shot migration: deterministic learned_skills -> macros table.

DEPRECATED: data migration is now handled by the Alembic migration
``366c99c58d20_separate_skill_and_macro.py``. This module is kept as a
compatibility shim so existing startup callers do not break.
"""

from __future__ import annotations


async def migrate_deterministic_skills() -> dict:
    """No-op: migration performed by Alembic."""
    return {"migrated": 0, "skipped": 0, "failed": 0}
