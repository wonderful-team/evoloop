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

    lines = [resolved["content"].strip()]
    base = resolved["base_dir"]
    if base:
        lines.append(f"\nBase directory for this skill: {base}")
        lines.append("Relative paths in this skill are relative to this base directory.")
    if resolved["files"]:
        lines.append("<skill_files>")
        lines.extend(resolved["files"])
        lines.append("</skill_files>")
    return "\n".join(lines)
