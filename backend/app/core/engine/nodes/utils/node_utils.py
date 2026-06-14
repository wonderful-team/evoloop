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
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
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

    try:
        from app.core import file as file_utils
        return file_utils.read_file(profile_path).content or ""
    except Exception as e:
        prefix = f"{log_prefix} " if log_prefix else ""
        logger.debug(f"{prefix}Failed to read PROJECT.md: {e}")
        return ""
