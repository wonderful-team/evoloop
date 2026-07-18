"""Entity grouping for the AppMap Agent — groups indexed files by domain entity."""

from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.database import session_scope
from app.models.codebase import Repository

from .generator import ClassifiedFile, EntityGrouper
from .llm_classifier import LLMFileClassifier, classify_files_with_llm

__all__ = [
    "EntityGrouper",
    "ClassifiedFile",
    "LLMFileClassifier",
    "classify_files_with_llm",
    "get_entity_groups",
]


async def get_entity_groups(project_id: int) -> dict[str, list[ClassifiedFile]]:
    """Return entity groups for *project_id* (resolves the active repo)."""
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
        return await EntityGrouper().get_entity_groups(repo_id, db)
