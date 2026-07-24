"""
Wiki page read-only service.

Generation is now handled by the Agent + Skill system (Wiki Generation SKILL.md).
This module only provides query utilities for the WikiPage table.
"""
import logging

from sqlmodel import Session, select

from app.infrastructure.database.resource_manager import db_resource_manager as rm
from app.models.wiki import WikiPage
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType

logger = logging.getLogger(__name__)


class WikiService:
    """
    Service for Wiki page queries.
    Write operations are performed by the Agent via write_wiki_page tool.
    """

    def get_pages(self, project_id: int, member_id: int | None = None) -> list[WikiPage]:
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
            statement = select(WikiPage.project_id).where(
                WikiPage.project_id.in_(project_ids)
            ).distinct()
            results = session.exec(statement).all()
            return set(results)

    def ensure_toc_page(self, project_id: int, user_lang: str = "English") -> WikiPage | None:
        """
        Ensure a Table of Contents page exists for the project.
        If missing, auto-generate one from existing pages.
        Called as a post-processing step after Agent-driven wiki generation.
        """
        with Session(rm.sync_engine) as session:
            existing_toc = session.exec(
                select(WikiPage).where(
                    WikiPage.project_id == project_id,
                    WikiPage.slug == "toc",
                )
            ).first()
            if existing_toc:
                return existing_toc

            pages = session.exec(
                select(WikiPage).where(WikiPage.project_id == project_id).order_by(WikiPage.order)
            ).all()
            if not pages:
                return None

            is_chinese = "chinese" in user_lang.lower() or "中文" in user_lang
            toc_title = "目录" if is_chinese else "Table of Contents"

            # Build tree
            root_pages = [p for p in pages if p.parent_id is None]
            child_map: dict[int, list[WikiPage]] = {}
            for p in pages:
                if p.parent_id:
                    child_map.setdefault(p.parent_id, []).append(p)

            def build_tree(pages_list: list[WikiPage], indent: int = 0) -> list[str]:
                lines = []
                for p in pages_list:
                    prefix = "  " * indent + "- "
                    lines.append(f"{prefix}[{p.title}]({p.slug})")
                    children = child_map.get(p.id, [])
                    if children:
                        lines.extend(build_tree(children, indent + 1))
                return lines

            toc_content_lines = [f"# {toc_title}", ""]
            if is_chinese:
                toc_content_lines.append("本文档包含以下页面：")
            else:
                toc_content_lines.append("This wiki contains the following pages:")
            toc_content_lines.append("")
            toc_content_lines.extend(build_tree(root_pages))
            toc_content_lines.append("")

            toc_page = WikiPage(
                project_id=project_id,
                title=toc_title,
                slug="toc",
                content="\n".join(toc_content_lines),
                parent_id=None,
                order=0,
            )
            session.add(toc_page)
            session.commit()
            session.refresh(toc_page)
            logger.info(f"[WikiService] Auto-created TOC page for project {project_id} ({toc_title})")
            return toc_page


wiki_service = WikiService()


@event_register()
class WikiEventSubscriber:
    @event_subscribe(SystemEventType.ARTIFACT_VALIDATION)
    async def on_artifact_validation(self, event):
        if event.item == "wiki":
            event.is_valid = len(wiki_service.get_pages(event.project_id)) > 0
