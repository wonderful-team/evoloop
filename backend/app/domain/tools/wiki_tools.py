import hashlib
import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Annotated

from sqlmodel import Session, select

from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import safe_read_with_hash, write_file_with_verification
from app.core.file.editor.engine import EditEngine
from app.core.monitoring.ui_actions import (
    get_global_mode_message,
    require_project_for_tool,
)
from app.core.tools import evoloop_tool, get_working_directory
from app.core.tools.base import InjectedToolArg
from app.domain.wiki.service import wiki_service
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.wiki import WikiPage
from app.utils.controller_response import ControllerResponse, PerceptionsFormatter

logger = logging.getLogger(__name__)

WIKI_SUBDIR = "docs/wiki"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_slug(title: str) -> str:
    """Generate a URL-friendly slug from a human-readable title."""
    normalized = unicodedata.normalize("NFKD", title)
    slug = "".join(
        c
        for c in normalized
        if unicodedata.category(c).startswith("L") or c.isdigit() or c == " "
    )
    slug = slug.lower().replace(" ", "-").replace("_", "-")[:50]
    slug = re.sub(r"-+", "-", slug).strip("-")

    if not slug:
        slug = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]

    return slug


def _get_wiki_dir(project_path: str) -> str:
    return os.path.join(project_path, WIKI_SUBDIR)


def _get_wiki_file_path(project_path: str, slug: str) -> str:
    return os.path.join(_get_wiki_dir(project_path), f"{slug}.md")


def _ensure_wiki_dir(project_path: str) -> None:
    os.makedirs(_get_wiki_dir(project_path), exist_ok=True)


def _resolve_project_path(config: RunnableConfig | None = None) -> str:
    """Get the current project working directory from tool context."""
    return get_working_directory(config)


async def _resolve_wiki_project_id() -> int | None:
    """Helper to resolve project ID with temp-project support (Scheme C)."""
    pid = ContextManager.resolve_project_id(allow_global=False, request_temp=True)
    if pid == 0:
        result = await require_project_for_tool(
            tool_name="wiki", tool_category="wiki", prompt="Please select a project to use Wiki:"
        )
        if isinstance(result, str):
            return None
        pid = result
    return pid


def _find_page_by_title(session: Session, project_id: int, title: str) -> WikiPage | None:
    """Find a wiki page by title (case-insensitive exact match, then fuzzy)."""
    stmt = select(WikiPage).where(WikiPage.project_id == project_id)
    pages = session.exec(stmt).all()

    target = title.lower().strip()

    # 1. Exact case-insensitive match
    for page in pages:
        if page.title.lower().strip() == target:
            return page

    # 2. Substring fuzzy match (fallback)
    for page in pages:
        pt = page.title.lower().strip()
        if target in pt or pt in target:
            return page

    return None


def _read_page_content(project_path: str, slug: str) -> str | None:
    """Read wiki page content from the filesystem."""
    file_path = _get_wiki_file_path(project_path, slug)
    if not os.path.exists(file_path):
        return None
    try:
        content, _, _ = safe_read_with_hash(file_path)
        return content
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[Wiki] Failed to read file {file_path}: {e}")
        return None


def _write_page_content(project_path: str, slug: str, content: str) -> None:
    """Write wiki page content to the filesystem."""
    _ensure_wiki_dir(project_path)
    file_path = _get_wiki_file_path(project_path, slug)
    write_file_with_verification(content, file_path)


def _sync_page_to_db(
    session: Session,
    project_id: int,
    title: str,
    slug: str,
    content: str,
    parent_id: int | None = None,
    order: int = 0,
) -> str:
    """Sync a wiki page record to the DB (index). Returns 'created' or 'updated'."""
    stmt = select(WikiPage).where(
        WikiPage.project_id == project_id, WikiPage.slug == slug
    )
    page = session.exec(stmt).first()
    now = datetime.utcnow()

    if page:
        page.title = title
        page.content = content
        page.parent_id = parent_id
        page.order = order
        page.updated_at = now
        action = "updated"
    else:
        page = WikiPage(
            project_id=project_id,
            title=title,
            slug=slug,
            content=content,
            parent_id=parent_id,
            order=order,
            created_at=now,
            updated_at=now,
        )
        session.add(page)
        action = "created"

    session.commit()
    return action


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@evoloop_tool(
    summary_template="evoloop.tool_summary.list_wiki_pages",
)
async def list_wiki_pages(config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    List all available Wiki pages for the current project.
    Returns a list of page titles.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return get_global_mode_message("wiki")

    project_path = _resolve_project_path(config)
    wiki_dir = _get_wiki_dir(project_path)

    # ------------------------------------------------------------------
    # Reconcile filesystem with DB index (filesystem is source of truth)
    # ------------------------------------------------------------------
    if os.path.isdir(wiki_dir):
        with Session(db_resource_manager.sync_engine) as session:
            for filename in os.listdir(wiki_dir):
                if not filename.endswith(".md"):
                    continue
                slug = filename[:-3]
                file_path = os.path.join(wiki_dir, filename)
                try:
                    content, _, _ = safe_read_with_hash(file_path)
                    stmt = select(WikiPage).where(
                        WikiPage.project_id == project_id,
                        WikiPage.slug == slug,
                    )
                    page = session.exec(stmt).first()
                    if page:
                        page.content = content
                        page.updated_at = datetime.utcnow()
                    else:
                        # Infer title from first H1 or fallback to slug
                        inferred_title = (
                            slug.replace("-", " ").replace("_", " ").title()
                        )
                        if content.strip():
                            first_line = content.strip().split("\n", 1)[0]
                            if first_line.startswith("#"):
                                inferred_title = first_line.lstrip("#").strip()
                        session.add(
                            WikiPage(
                                project_id=project_id,
                                title=inferred_title,
                                slug=slug,
                                content=content,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow(),
                            )
                        )
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"[Wiki] Failed to sync file {file_path}: {e}")
            session.commit()

    pages = wiki_service.get_pages(project_id)
    if not pages:
        return ControllerResponse.error(
            f"No Wiki pages found for project {project_id}."
        ), {"count": 0}

    return PerceptionsFormatter.wiki_pages(pages), {"count": len(pages)}


@evoloop_tool(
    summary_template="evoloop.tool_summary.read_wiki_page",
)
async def read_wiki_page(title: str, config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    Read the content of a specific Wiki page by its title.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return get_global_mode_message("wiki")

    project_path = _resolve_project_path(config)

    with Session(db_resource_manager.sync_engine) as session:
        page = _find_page_by_title(session, project_id, title)
        if not page:
            return ControllerResponse.not_found(title, item_type="Wiki page")

        # Extract values before session closes (avoid detached instance errors)
        page_title = page.title
        page_slug = page.slug

        # Filesystem is source of truth
        content = _read_page_content(project_path, page_slug)

        if content is not None:
            if page.content != content:
                page.content = content
                page.updated_at = datetime.utcnow()
                session.commit()
        else:
            # File missing but DB has record — restore from DB
            content = page.content
            _write_page_content(project_path, page_slug, content)

    return ControllerResponse.success(
        f"Wiki Page: {page_title}",
        details=content,
        note=f"Title: {page_title}",
    )


@evoloop_tool(
    is_state_mutating=True,
    required_benefit="wiki_generation",
    summary_template="evoloop.tool_summary.write_wiki_page",
)
async def write_wiki_page(
    title: str,
    content: str,
    parent_title: str | None = None,
    order: int = 0,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create or update a Wiki page in the current project.

    Args:
        title: The display title of the page. Used as the natural-language address.
        content: The Markdown content of the page.
        parent_title: Optional title of the parent page for hierarchy.
        order: Sorting order among siblings.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return ControllerResponse.error("Wiki requires a project.")

    project_path = _resolve_project_path(config)

    # Generate slug from title
    slug = _generate_slug(title)

    # No special case for TOC slugs anymore, rely on title-derived slugs or user-defined hierarchy

    with Session(db_resource_manager.sync_engine) as session:
        # If a page with this title already exists, reuse its slug
        existing = _find_page_by_title(session, project_id, title)
        if existing:
            slug = existing.slug

        parent_id = None
        parent_hint = None
        if parent_title:
            parent = _find_page_by_title(session, project_id, parent_title)
            if parent:
                parent_id = parent.id
            else:
                parent_hint = (
                    f"Warning: Parent page '{parent_title}' not found. "
                    "Make sure you create the parent page BEFORE its children, "
                    "and that the title matches exactly (including case)."
                )

        # Write to filesystem (source of truth)
        _write_page_content(project_path, slug, content)

        # Sync to DB index
        action = _sync_page_to_db(
            session,
            project_id,
            title,
            slug,
            content,
            parent_id=parent_id,
            order=order,
        )

    note = None
    if action == "updated":
        note = (
            f"WARNING: This page already existed and was OVERWRITTEN. "
            f"If you did not intend to update '{title}', check your plan and avoid duplicate work. "
            f"Consider using edit_wiki_page() for incremental changes."
        )

    return ControllerResponse.action_result(
        action=action,
        target=title,
        success=True,
        details=f"Title: {title}",
        note=note or parent_hint,
    )


@evoloop_tool(
    is_state_mutating=True,
    required_benefit="wiki_generation",
    summary_template="evoloop.tool_summary.edit_wiki_page",
)
async def edit_wiki_page(
    title: str,
    old_string: str,
    new_string: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Incrementally edit a Wiki page by replacing a section of text.

    This uses fuzzy matching to locate `old_string` inside the page.
    Provide enough surrounding lines in `old_string` to ensure uniqueness.

    Args:
        title: The title of the page to edit.
        old_string: The text to find and replace. Must be actual page content.
        new_string: The replacement text.
    """
    project_id = await _resolve_wiki_project_id()
    if project_id is None:
        return ControllerResponse.error("Wiki requires a project.")

    if len(old_string.strip()) < 3:
        return ControllerResponse.error(
            "Target text too short (must be > 2 characters). "
            "Provide more surrounding context to ensure unique matching."
        )

    project_path = _resolve_project_path(config)

    with Session(db_resource_manager.sync_engine) as session:
        page = _find_page_by_title(session, project_id, title)
        if not page:
            return ControllerResponse.not_found(title, item_type="Wiki page")

        # Extract values before session closes (avoid detached instance errors)
        page_title = page.title
        page_slug = page.slug
        page_content = page.content

        file_path = _get_wiki_file_path(project_path, page_slug)

        # If file is missing, restore from DB before editing
        if not os.path.exists(file_path):
            _write_page_content(project_path, page_slug, page_content)

        content, _, _ = safe_read_with_hash(file_path)

        # Apply replacement via EditEngine (cascading fuzzy matching)
        success, new_content, log = EditEngine.apply_replacement(
            content, old_string, new_string, replace_all=False
        )

        if not success:
            return ControllerResponse.error(
                f"Could not find the target text in page '{title}'.",
                details=log,
                note="Expand old_string with more surrounding lines to make it unique.",
            )

        # Write back
        write_result = write_file_with_verification(new_content, file_path)
        if not write_result.get("success"):
            return ControllerResponse.error(
                "Edit matched but write failed.",
                details=write_result.get("message"),
            )

        # Sync updated content to DB index
        _sync_page_to_db(session, project_id, page_title, page_slug, new_content)

    return ControllerResponse.success(
        f"Updated page: {page_title}",
        details=f"Changed: {old_string[:50]}{'...' if len(old_string) > 50 else ''}",
        note=f"Title: {page_title}",
    )
