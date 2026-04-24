import logging
import os
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


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
    Standardizes and maps the CWD for Agent prompts.
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
