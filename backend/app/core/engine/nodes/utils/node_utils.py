"""
Shared utilities for EvoLoop engine nodes.

Extracts cross-cutting concerns (logging, state resolution, signal dispatch)
to eliminate duplication across BaseAgentNode, FinishNode, SupervisorNode, etc.
"""

import logging
import os
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.execution.execution_mode import is_docker_mode
from app.core.project.utils import get_workspace_root
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


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
            res["metadata"] = obj.metadata
        return to_template_context(res)
    if isinstance(obj, list):
        return [to_template_context(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_template_context(v) for k, v in obj.items()}
    return obj


def get_mapped_cwd(ctx_cwd: str) -> str:
    """
    Standardizes and maps the CWD for Agent prompts and execution context.
    If the process runs with the docker sandbox, maps host paths to /workspace.

    基于事实层（execution_mode.is_docker_mode）判定，不读取 SystemConfig 覆写：
    运行时 worker 与 prompt 渲染都必须跟随进程真实模式，避免覆写导致路径
    被映射进不存在的 /workspace。
    """
    actual_cwd = ctx_cwd or ""

    if is_docker_mode():
        workspace_root = get_workspace_root()
        if workspace_root:
            workspace_root = os.path.normpath(workspace_root)
            actual_cwd = os.path.normpath(actual_cwd)
            if actual_cwd.startswith(workspace_root):
                rel_part = actual_cwd[len(workspace_root) :].lstrip("/")
                actual_cwd = (
                    os.path.join("/workspace", rel_part) if rel_part else "/workspace"
                )

    return actual_cwd


def get_displayed_execution_mode() -> str:
    """Returns the execution mode shown in prompt/template rendering (local/docker).

    表现层：允许 SystemConfig 表覆写（例如在运营后台把某个环境的展示模式切到
    docker），回退到进程真实模式。仅供 prompt 渲染；沙箱构建与 HITL 豁免一律
    使用事实层 ``execution_mode.get_execution_mode``，不读此处。
    """
    mode = SystemConfigService.get_value("EXECUTION_MODE") or settings.EXECUTION_MODE
    return str(mode).lower()


def read_project_profile(working_directory: str | None, _log_prefix: str = "") -> str:
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
