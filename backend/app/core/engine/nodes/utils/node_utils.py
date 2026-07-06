"""
Shared utilities for EvoLoop engine nodes.

Extracts cross-cutting concerns (logging, state resolution, signal dispatch)
to eliminate duplication across BaseAgentNode, FinishNode, AggregatorNode, etc.
"""

import logging
import os
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


def resolve_is_subtask(state: Any) -> bool:
    """
    Resolve `is_subtask` from state.
    """
    return state.is_subtask


def to_template_context(obj: Any) -> Any:
    """Recursively convert Pydantic models to JSON-safe plain Python objects for Jinja2."""
    if obj is None:
        return None
    # Check if it is an SQLAlchemy model
    if hasattr(obj, "__table__"):
        try:
            res = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
            return to_template_context(res)
        except AttributeError:
            return str(obj)
    if isinstance(obj, BaseModel):
        res = obj.model_dump()
        if hasattr(obj, "metadata") and "metadata" not in res:
            res["metadata"] = getattr(obj, "metadata")
        return to_template_context(res)
    if isinstance(obj, list):
        return [to_template_context(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_template_context(v) for k, v in obj.items()}
    return obj


def get_mapped_cwd(ctx_cwd: str) -> str:
    """
    Standardizes and maps the CWD for Agent prompts and execution context.
    If in Docker mode, maps host paths to /workspace.
    """
    mode = SystemConfigService.get_value("EXECUTION_MODE") or settings.EXECUTION_MODE
    actual_cwd = ctx_cwd or ""

    if str(mode).lower() == "docker":
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        if workspace_root:
            workspace_root = os.path.normpath(workspace_root)
            actual_cwd = os.path.normpath(actual_cwd)
            if actual_cwd.startswith(workspace_root):
                rel_part = actual_cwd[len(workspace_root):].lstrip("/")
                actual_cwd = os.path.join("/workspace", rel_part) if rel_part else "/workspace"

    return actual_cwd


def get_sandbox_mode() -> str:
    """Returns the current execution mode (local/docker)."""
    mode = SystemConfigService.get_value("EXECUTION_MODE") or settings.EXECUTION_MODE
    return str(mode).lower()


def read_project_profile(working_directory: str | None, log_prefix: str = "") -> str:
    """Read PROJECT.md from the given working directory if it exists.

    Returns the file content or an empty string if the file is missing or unreadable.
    """
    if not working_directory:
        return ""

    profile_path = os.path.join(working_directory, "PROJECT.md")
    if not os.path.isfile(profile_path):
        return ""

    from app.core import file as file_utils
    return file_utils.read_file(profile_path).content or ""


async def read_wiki_index(project_id: int | None, limit: int = 20) -> list[dict]:
    """Read project wiki page index (title + summary) for prompt injection.

    Returns a list of {"title": ..., "summary": ...} dicts, sorted by updated_at desc.
    Returns empty list in global mode (project_id=0 or None).
    """
    from app.constants import DEFAULT_PROJECT_ID

    if not project_id or project_id == DEFAULT_PROJECT_ID:
        return []

    try:
        from sqlalchemy import select
        from app.infrastructure.database import session_scope
        from app.models.wiki import WikiPage

        async with session_scope() as session:
            stmt = (
                select(WikiPage.id, WikiPage.title, WikiPage.content, WikiPage.updated_at)
                .where(WikiPage.project_id == project_id)
                .order_by(WikiPage.updated_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "title": row.title,
                    "summary": (row.content[:100] + "...") if row.content and len(row.content) > 100 else (row.content or ""),
                }
                for row in rows
            ]
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[read_wiki_index] Failed to load wiki index: {e}")
        return []
