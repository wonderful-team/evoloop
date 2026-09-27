"""多租户 agent 视角路径换算（模块 6：提示词/工具输出的容器面清洗）。

所有注入 prompt / 工具返回给 agent 的路径，必须经过本模块换算：
宿主真实路径（如 ``/www/wwwroot/evoloop/workspace/<member>/x``）一律呈现为
``/workspace[/相对路径]``，宿主机结构不得进入对话面。
"""

from __future__ import annotations

import os

from app.core.config import settings
from app.core.project.utils import current_member_id, resolve_member_workspace_root


def to_agent_view_path(path: str | None) -> str | None:
    """将宿主路径换算为 agent 可见路径；多租户下越界路径返回 None（不该出现）。

    单用户模式原样返回（无隔离语义，宿主即工作区）。
    """
    if not path:
        return path
    if not settings.MULTI_TENANT_MODE:
        return path
    member_root = resolve_member_workspace_root(current_member_id())
    if not member_root:
        return None
    normalized = os.path.realpath(path)
    root = os.path.realpath(member_root)
    if normalized == root:
        return "/workspace"
    if normalized.startswith(root + os.sep):
        return "/workspace" + normalized[len(root):]
    return None

