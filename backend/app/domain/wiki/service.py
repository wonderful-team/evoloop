"""
Wiki page read-only service.

Generation is now handled by the Agent + Skill system (Wiki Generation SKILL.md).
This module only provides query utilities for the WikiPage table.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from app.constants import DEFAULT_PROJECT_ID
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.infrastructure.database.resource_manager import db_resource_manager as rm
from app.models.wiki import WikiPage

logger = logging.getLogger(__name__)


class WikiService:
    """
    Service for Wiki page queries.
    Write operations are performed by the Agent via write_wiki_page tool.
    """

    def get_pages(
        self, project_id: int, member_id: int | None = None
    ) -> list[WikiPage]:
        with Session(rm.sync_engine) as session:
            statement = select(WikiPage).where(WikiPage.project_id == project_id)
            if member_id is not None:
                statement = statement.where(WikiPage.member_id == member_id)
            statement = statement.order_by(WikiPage.order)
            results = session.exec(statement)
            return results.all()

    def get_page(self, page_id: int) -> WikiPage | None:
        with Session(rm.sync_engine) as session:
            return session.get(WikiPage, page_id)

    def get_projects_with_wiki(self, project_ids: list[int]) -> set[int]:
        """
        Efficiently check which projects have wiki pages.
        """
        if not project_ids:
            return set()
        with Session(rm.sync_engine) as session:
            statement = (
                select(WikiPage.project_id)
                .where(WikiPage.project_id.in_(project_ids))
                .distinct()
            )
            results = session.exec(statement).all()
            return set(results)

    def get_wiki_index(self, project_id: int | None, limit: int = 20) -> list[dict]:
        """
        Read project wiki page index (title + summary) for prompt injection.

        Returns a list of {"title": ..., "summary": ...} dicts, sorted by
        updated_at desc. Returns empty list in global mode (project_id=0 or None).

        Wiki index is advisory prompt context: a database-level failure degrades
        to an empty list (logged with traceback) instead of crashing prompt
        construction, while genuine code bugs (TypeError etc.) still fail fast.
        """
        if not project_id or project_id == DEFAULT_PROJECT_ID:
            return []

        try:
            with Session(rm.sync_engine) as session:
                statement = (
                    select(
                        WikiPage.id,
                        WikiPage.title,
                        WikiPage.content,
                        WikiPage.updated_at,
                    )
                    .where(WikiPage.project_id == project_id)
                    .order_by(WikiPage.updated_at.desc())
                    .limit(limit)
                )
                rows = session.exec(statement).all()
                return [
                    {
                        "title": row.title,
                        "summary": (
                            row.content[:100] + "..."
                            if row.content and len(row.content) > 100
                            else (row.content or "")
                        ),
                    }
                    for row in rows
                ]
        except DBAPIError:
            logger.exception(
                "[WikiService] Failed to load wiki index for project %s", project_id
            )
            return []

wiki_service = WikiService()


@event_register()
class WikiEventSubscriber:
    @event_subscribe(SystemEventType.ARTIFACT_VALIDATION)
    async def on_artifact_validation(self, event):
        if event.item == "wiki":
            event.is_valid = len(wiki_service.get_pages(event.project_id)) > 0
