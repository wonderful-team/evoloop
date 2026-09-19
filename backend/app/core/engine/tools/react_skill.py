"""React engine `skill` tool — load a skill on demand (OpenCode `tool/skill.ts`, §5).

索引（<available_skills>）在 system prompt，正文按需加载。调用 ``skill(name)``
返回完整 SKILL 正文 + 基础目录 + 资源文件列表（<skill_files>），脚本/模板
经文件列表路径用 read 读取。加载后的正文即普通 tool result 进入消息流。
"""

from __future__ import annotations

import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(is_hidden=False)
async def skill(
    name: str,
) -> str:
    """按需加载一个专业化技能（skill）。

    当手头任务匹配系统提示中 <available_skills> 索引里的某个技能时，加载其 SKILL.md 正文并按
    指令执行。索引在 system prompt，正文按需加载；调用后返回完整 SKILL 正文 + 基础目录 +
    资源文件列表（<skill_files>），脚本/模板经文件列表路径用 read 读取。

    When to use:
    - 任务匹配 <available_skills> 索引中某个技能（如代码生成 / 值守巡检 / 特定工作流）时，
      加载其 SKILL.md 正文并按指令执行。
    - 主动使用：当任务明显对应某个技能（写宏 / 画图 / 值守 / 特定领域流程）时，即使没被
      显式要求也应主动加载该技能——技能里往往有必须遵守的工作流与模板，跳过会做错。

    When NOT to use:
    - 只是读文件/搜索代码时用 read / glob / grep 更快，不要加载技能。
    - 技能名不在 <available_skills> 中时先说明找不到，不要猜名。

    Usage notes:
    1. name 必须精确匹配 <available_skills> 中的技能名。
    2. 加载后按 SKILL.md 正文行动；引用的脚本/模板用 <skill_files> 中的相对路径经 read 读取。

    Args:
        name: 技能名（来自 <available_skills> 索引）。
    """
    from app.core.engine.react.skills.manager import resolve_skill

    try:
        resolved = await resolve_skill(name)
    except Exception as e:
        logger.exception(f"[SkillTool] Failed to resolve skill '{name}': {e}")
        return f"Error: failed to load skill '{name}': {e}"

    if not resolved:
        return (
            f"Error: skill '{name}' not found in <available_skills>. "
            "Do not guess names; only load skills listed in the system prompt."
        )

    activated_note = await _activate_package_capability(resolved)

    lines = [resolved["content"].strip()]
    base = resolved["base_dir"]
    if base:
        lines.append(f"\nBase directory for this skill: {base}")
        lines.append("Relative paths in this skill are relative to this base directory.")
    if resolved["files"]:
        lines.append("<skill_files>")
        lines.extend(resolved["files"])
        lines.append("</skill_files>")
    if activated_note:
        lines.append(activated_note)
    return "\n".join(lines)


async def _activate_package_capability(resolved: dict) -> str:
    """能力包加载联动（capability-packages-refactor.md §6-#3）。

    包类技能（capability.tools 声明）加载时：
    1. 逐 server ``ensure_connected``（连接进程级持久，幂等）；
    2. 包名并入 ``ctx.metadata.loaded_packages``（EvoContext 随 thread 持久，
       下一轮 ToolManager 按 (server, tool) 解析可见性）。

    Returns:
        附给 LLM 的提示文本（工具下一轮可用）；非包技能返回空串。
    """
    capability = resolved.get("capability")
    if not capability:
        return ""

    package_name = resolved.get("name") or ""
    servers: list[str] = []
    for entry in capability.get("tools") or []:
        server = entry.get("mcp_server")
        if isinstance(server, str) and server and server not in servers:
            servers.append(server)

    notes: list[str] = []
    failed_servers: list[str] = []
    if servers:
        from app.core.mcp import mcp_client_manager

        for server_name in servers:
            connected = await mcp_client_manager.ensure_connected(server_name)
            if not connected:
                failed_servers.append(server_name)
            notes.append(
                f"MCP server '{server_name}' connected: yes"
                if connected
                else f"MCP server '{server_name}' connected: FAILED (tools unavailable)"
            )

    # 审计修订（2026-09-18，外部连接不可靠是常态）：记账条件从「server 全部
    # 连接成功」改为「SOP 正文已交付」。原 all_connected 门在 server 故障时
    # 阻止记账，导致故障恢复后工具面也不会自愈（包不在 loaded 集内，须 Agent
    # 手动重调 skill）——把「暂时连不上」升级成了「永久搁浅」。现语义：
    # 1. 记账 = SOP 已读（G4 前提满足），与连接状态解耦；
    # 2. 工具可见性永远反映真实状态：server 未连接时 aget_all_tools 本就不
    #    返回其工具，不存在「解锁了坏工具」；恢复后下一轮 get_agent_tools
    #    自动出现（ensure_connected 每轮重试）——故障只降级可见性，不阻断任务；
    # 3. 返回给 LLM 的降级报告给出明确行动指引，防止用 bash 绕过（安全钩子
    #    会拦截 .evoloop/MCP 内部访问，实测会白烧轮次）。
    try:
        from app.core.context import ContextManager

        ctx = ContextManager.current()
        loaded = ctx.metadata.loaded_packages
        if package_name and package_name not in loaded:
            loaded.append(package_name)
            # bind_tools 每次 delivery 只绑一次；置脏标记，inference 循环
            # 每步检测并 rebind，本 run 内立即可用。
            ctx.metadata.packages_dirty = True

        # 包反哺会话域（自动识别）：把包声明的 capability.domain 记为会话域
        # （last-loaded-wins 证据）。优先级裁决在装配解析处
        # （capability_profiles.resolve_profile_candidates）：hint 域若不可
        # 装配（如分类器标签与包目录词汇不一致），不得阻塞可装配的反哺域。
        cap_domain = capability.get("domain")
        if cap_domain and ctx.metadata.session_domain != cap_domain:
            ctx.metadata.session_domain = cap_domain
            logger.info(
                "[SkillTool] session domain feedback: '%s' (from package '%s')",
                cap_domain,
                package_name,
            )
    except Exception:
        logger.exception("[SkillTool] failed to record loaded package '%s'", package_name)

    if failed_servers:
        notes.append(
            f"Package activated with DEGRADED capability: "
            f"{len(servers) - len(failed_servers)}/{len(servers)} MCP server(s) available; "
            f"unavailable: {', '.join(failed_servers)}."
        )
        notes.append(
            "Tools from unavailable servers will appear automatically once they "
            "reconnect (connection is re-checked every turn) — the task can "
            "proceed without them. Do NOT try to access MCP internals or "
            ".evoloop via bash (blocked by security policy); if the data is "
            "blocking, retry skill(name) later or inform the user."
        )

    return "\n".join(notes)
