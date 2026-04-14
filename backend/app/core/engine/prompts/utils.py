import logging
import os

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


def get_mapped_cwd(ctx_cwd: str) -> str:
    """
    Standardizes and maps the CWD for Agent prompts.
    If in Docker mode, maps host paths to /workspace.
    """
    mode = SystemConfigService.get_value("EXECUTION_MODE") or settings.EXECUTION_MODE
    actual_cwd = ctx_cwd or ""
    
    if str(mode).lower() == "docker":
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT") or settings.WORKSPACE_ROOT
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
