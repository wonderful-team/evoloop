"""Skill loader for the React engine (OpenCode `skill` tool semantic, §5.6).

SKILL 是"索引注入 + 按需加载"两段式：
- system prompt 只放 <available_skills> 索引（name+description，见 react/prompts.py）；
- 模型按需调用 ``skill(name)`` 工具，本模块返回完整 SKILL 正文 + 基础目录 +
  资源文件列表（<skill_files>），作为普通 tool result 进入消息流。

数据源复用 ``skill_discovery``（DB LearnedSkill，含文件导入的 resource_path）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.core.learning.skills.discovery import skill_discovery

logger = logging.getLogger(__name__)

#: <skill_files> 最多列出的资源文件数
MAX_SKILL_FILES = 10


async def resolve_skill(name: str) -> dict[str, Any] | None:
    """按名称解析技能，返回正文 + 基础目录 + 资源文件列表。

    Returns:
        形如 ``{"content", "base_dir", "files"}`` 的 dict；未找到返回 None。
    """
    match, relevant, _ = await skill_discovery.exact_search(str(name).strip())
    if not match or not relevant:
        return None

    skill = relevant[0]
    base_dir = getattr(skill, "resource_path", None) or ""
    files: list[str] = []
    if base_dir and os.path.isdir(base_dir):
        try:
            entries = sorted(
                f
                for f in os.listdir(base_dir)
                if os.path.isfile(os.path.join(base_dir, f))
                and not f.lower().startswith("skill.md")
            )
            files = entries[:MAX_SKILL_FILES]
        except OSError as e:
            logger.warning(f"[SkillTool] Failed to list skill files for {name}: {e}")

    content = f"# Skill: {skill.name}\n\n"
    if getattr(skill, "description", None):
        content += f"{skill.description}\n\n"
    if getattr(skill, "instructions", None):
        content += skill.instructions.strip() + "\n"

    return {
        "content": content,
        "base_dir": base_dir,
        "files": files,
        "name": skill.name,
    }
