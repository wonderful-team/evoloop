"""页面级包预选（capability-packages-refactor.md v3，§6-#6）。

域 → 包目录：DB 查询（包自声明 capability.domain，v3 收敛——作用域模型统一，
profile 的 packages 字段删除）。页面预挂：host_ctx.route 经包 route_patterns
匹配。预选集每轮确定性重算（preselected_packages），加载集（loaded_packages）
由 Agent skill 加载增量叠加。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def resolve_preselection(
    domain: str | None,
    host_ctx: dict[str, Any] | None,
) -> list[str]:
    """页面级预选：域内包按 route_patterns 匹配 host_ctx.route。

    Returns:
        预挂包名列表（0-1 个，v1 边界：单包预挂）；无信号/无包返回空。
    """
    if not domain:
        return []
    from app.core.learning.skills.discovery import skill_discovery

    packages = await skill_discovery.get_packages_for_domain(domain)
    if not packages:
        return []

    route = ""
    if isinstance(host_ctx, dict):
        route = str(host_ctx.get("route") or "").strip().lower()
    if not route:
        return []

    for pkg in packages:
        patterns = (pkg.capability or {}).get("route_patterns") or []
        for pattern in patterns:
            pat = str(pattern).strip().lower()
            if pat and route.startswith(pat):
                return [pkg.name]
    return []


async def preload_preselection(packages: list[str], ctx: Any) -> None:
    """预挂接线：预选包逐 server ensure_connected + 写 preselected_packages。

    G4 写操作边界：预挂面由 ToolManager 按 confirm_tools 排除写工具
    （SOP 未读须显式加载包后放开）。
    """
    if not packages:
        # 无预选也要清空残留（每轮确定性重算；否则上一轮预选的包
        # 在无域/无路由轮次持续残留，G4 排除面与工具面错误延续）
        ctx.metadata.preselected_packages = []
        return
    ctx.metadata.preselected_packages = list(packages)
    from app.core.learning.skills.discovery import skill_discovery
    from app.core.mcp import mcp_client_manager

    servers: list[str] = []
    for pkg in packages:
        # 审计修复：此前用 get_packages_for_domain(None) 查包——该函数
        # domain 为空恒返回 []，导致预挂包的 server 从不 ensure_connected
        # （死代码回归）。按名查包的 capability 声明（O(1) 内存索引）。
        capability = await skill_discovery.get_capability(pkg)
        if not capability:
            continue
        for entry in capability.get("tools") or []:
            server = entry.get("mcp_server")
            if isinstance(server, str) and server and server not in servers:
                servers.append(server)
    for server_name in servers:
        try:
            await mcp_client_manager.ensure_connected(server_name)
        except Exception:
            logger.exception(
                "[Preselection] preload connect failed for %s", server_name
            )
