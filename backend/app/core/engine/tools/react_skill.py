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
    all_connected = True
    if servers:
        from app.core.mcp import mcp_client_manager

        for server_name in servers:
            connected = await mcp_client_manager.ensure_connected(server_name)
            if not connected:
                all_connected = False
            notes.append(
                f"MCP server '{server_name}' connected: yes"
                if connected
                else f"MCP server '{server_name}' connected: FAILED (tools unavailable)"
            )

    # 审计修复：server 连接失败时不得记账为已加载（否则 G4 按「已加载=全量」
    # 解锁写工具，调用必然失败且无失效机制）。连接全失败时不激活。
    if all_connected:
        try:
            from app.core.context import ContextManager

            ctx = ContextManager.current()
            loaded = ctx.metadata.loaded_packages
            if package_name and package_name not in loaded:
                loaded.append(package_name)
                # 审计修复：bind_tools 每次 delivery 只绑一次，此前激活的新
                # 工具要等下一次 delivery 才可达（同 run 内必然 not found →
                # doom loop）。置脏标记，inference 循环每步检测并 rebind，
                # 本 run 内立即可用。
                ctx.metadata.packages_dirty = True
        except Exception:
            logger.exception("[SkillTool] failed to record loaded package '%s'", package_name)
    else:
        notes.append(
            "Package NOT activated (server unavailable): tools remain locked. "
            "Retry later or use the tools after the server recovers."
        )

    return "\n".join(notes)
