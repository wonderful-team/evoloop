import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from sqlmodel import Session, select

from app.core.context.manager import ContextManager
from app.core.monitoring.ui_actions import get_global_mode_message, require_project_for_tool
from app.core.tools import evoloop_tool
from app.domain.wiki.service import wiki_service
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.wiki import WikiPage
from app.utils import ControllerResponse, PerceptionsFormatter, render_template

logger = logging.getLogger(__name__)


async def _resolve_wiki_project_id() -> int | None:
    """Helper to resolve project ID with temp project support (Scheme C)."""
    pid = ContextManager.resolve_project_id(allow_global=False, request_temp=True)

    if pid == 0:
        result = await require_project_for_tool(
            tool_name="wiki",
            tool_category="wiki",
            prompt="Please select a project to use Wiki:"
        )
        if isinstance(result, str):
            return None  # User cancelled
        pid = result

    return pid


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.list_wiki_pages"
)
async def list_wiki_pages(
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    List all available Wiki pages for the current project.
    Returns a list of page titles and slugs.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return get_global_mode_message("wiki")

    pages = wiki_service.get_pages(project_id)
    if not pages:
        return ControllerResponse.error(f"No Wiki pages found for project {project_id}."), {"count": 0}

    return PerceptionsFormatter.wiki_pages(pages), {"count": len(pages)}


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.read_wiki_page"
)
async def read_wiki_page(
    slug: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Read the content of a specific Wiki page by its slug.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return get_global_mode_message("wiki")

    with Session(db_resource_manager.sync_engine) as session:
        stmt = select(WikiPage).where(
            WikiPage.project_id == project_id,
            WikiPage.slug == slug
        )
        page = session.exec(stmt).first()

        if not page:
            return ControllerResponse.not_found(slug, item_type="Wiki page")

        return ControllerResponse.success(
            f"Wiki Page: {page.title}",
            details=page.content,
            note=f"Slug: {page.slug}"
        )


@evoloop_tool(
    is_state_mutating=True,
    required_benefit="wiki_generation",
    summary_template="evoloop.tool_summary.write_wiki_page"
)
async def write_wiki_page(
    title: str,
    content: str,
    slug: str | None = None,
    parent_slug: str | None = None,
    order: int = 0,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Create or update a Wiki page in the current project.

    Args:
        title: The display title of the page.
        content: The Markdown content of the page.
        slug: Optional slug. If not provided, it will be generated from the title.
        parent_slug: Optional slug of the parent page for hierarchy.
        order: Sorting order among siblings.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return render_template("common/report/response.prompt.j2", 
                              success=False, 
                              message="Wiki requires a project.", 
                              note="Global Mode")

    # 1. Generate slug if needed
    if not slug:
        import re
        slug = title.lower().replace(" ", "-").replace("_", "-")
        slug = re.sub(r'[^a-z0-9-]', '', slug)[:50]

    # 2. Find parent_id if parent_slug provided
    parent_id = None
    if parent_slug:
        with Session(db_resource_manager.sync_engine) as session:
            parent_stmt = select(WikiPage).where(
                WikiPage.project_id == project_id,
                WikiPage.slug == parent_slug
            )
            parent = session.exec(parent_stmt).first()
            if parent:
                parent_id = parent.id
            else:
                return f"Error: Parent page with slug '{parent_slug}' not found."

    # 3. Create or Update
    with Session(db_resource_manager.sync_engine) as session:
        stmt = select(WikiPage).where(
            WikiPage.project_id == project_id,
            WikiPage.slug == slug
        )
        existing_page = session.exec(stmt).first()

        if existing_page:
            existing_page.title = title
            existing_page.content = content
            existing_page.parent_id = parent_id
            existing_page.order = order
            session.add(existing_page)
            action = "Updated"
        else:
            new_page = WikiPage(
                project_id=project_id,
                title=title,
                slug=slug,
                content=content,
                parent_id=parent_id,
                order=order
            )
            session.add(new_page)
            action = "Created"

        session.commit()

    return ControllerResponse.action_result(
        action=action.lower(),
        target=title,
        success=True,
        details=f"Slug: {slug}"
    )
