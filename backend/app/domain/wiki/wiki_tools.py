import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from app.utils import render_template
from langchain_core.tools import InjectedToolArg
from sqlmodel import Session, select

from app.core.context.manager import ContextManager
from app.core.db import engine
from app.core.tools import evoloop_tool
from app.domain.wiki.service import wiki_service
from app.models.wiki import WikiPage

logger = logging.getLogger(__name__)


@evoloop_tool
async def list_wiki_pages(
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    List all available Wiki pages for the current project.
    Returns a list of page titles and slugs.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id

    if not project_id:
        return "Error: No active project context. Please ensure project_id is set."

    pages = wiki_service.get_pages(project_id)
    if not pages:
        return f"No Wiki pages found for project {project_id}."

    try:
        pages_data = [{"path": p.slug, "content": f"(Title: {p.title})"} for p in pages]
        return render_template("wiki/wiki_context.prompt.j2", files=pages_data)
    except Exception as e:
        logger.error(f"Failed to render wiki page list: {e}")
        return "\n".join([f"- {p.title} (slug: {p.slug})" for p in pages])


@evoloop_tool
async def read_wiki_page(
    slug: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Read the content of a specific Wiki page by its slug.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id

    if not project_id:
        return "Error: No active project context."

    with Session(engine) as session:
        stmt = select(WikiPage).where(
            WikiPage.project_id == project_id,
            WikiPage.slug == slug
        )
        page = session.exec(stmt).first()

        if not page:
            return f"Error: Wiki page with slug '{slug}' not found in project {project_id}."

        return f"--- Wiki Page: {page.title} ({page.slug}) ---\n\n{page.content}"


@evoloop_tool
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
    ctx = ContextManager.current()
    project_id = ctx.project_id

    if not project_id:
        return "Error: No active project context."

    # 1. Generate slug if needed
    if not slug:
        import re
        slug = title.lower().replace(" ", "-").replace("_", "-")
        slug = re.sub(r'[^a-z0-9-]', '', slug)[:50]

    # 2. Find parent_id if parent_slug provided
    parent_id = None
    if parent_slug:
        with Session(engine) as session:
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
    with Session(engine) as session:
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

    return f"Successfully {action} Wiki page: {title} ({slug})"
