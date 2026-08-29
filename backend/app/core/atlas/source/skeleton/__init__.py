"""Entity grouping for the AppMap Agent — groups indexed files by domain entity."""

from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.database import session_scope
from app.models.codebase import Repository

from .generator import ClassifiedFile, EntityGrouper

__all__ = [
    "EntityGrouper",
    "ClassifiedFile",
    "get_entity_groups",
]


async def get_entity_groups(project_id: int, project_path: str | None = None) -> dict:
    """Return entity groups for *project_id* (resolves the active repo).

    Args:
        project_id: Target project ID.
        project_path: Optional project root path. When provided, EntityGrouper
                      reads framework_profile.role_classifiers for dynamic rules.
    """
    async with session_scope() as db:
        stmt = (
            select(Repository.id)
            .where(
                Repository.project_id == project_id,
                Repository.sync_status.not_in(("IGNORED", "DISCONNECTED")),
            )
            .order_by(Repository.id)
        )
        result = await db.execute(stmt)
        repo_id = result.scalar_one_or_none()
    if repo_id is None:
        return {}
    async with session_scope() as db:
        return await EntityGrouper(project_path=project_path).get_entity_groups(
            repo_id, db
        )
