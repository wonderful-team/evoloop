"""
Skill Synthesizer 共享工具函数

提取 WorkflowSynthesizer 和 MultimodalSkillSynthesizer 的重复逻辑，
避免代码重复，提高可维护性。
"""

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.file import ensure_dir
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.learning import LearnedSkill
from app.utils.extract import extract_section as _extract_section
from app.utils.extract import extract_yaml_block as _extract_yaml_block
from app.utils.yaml import safe_yaml_dumps

logger = logging.getLogger(__name__)


class SkillExportModel(DynamicBaseModel):
    name: str
    namespace: str = "misc"
    description: str = ""
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[Any] = Field(default_factory=list)
    preconditions: list[Any] = Field(default_factory=list)
    instructions: str | None = None


def export_skill_to_filesystem(skill_data: LearnedSkill | dict[str, Any]) -> str | None:
    """
    导出技能到文件系统 (SKILL.md)
    """
    try:
        if isinstance(skill_data, dict):
            export = SkillExportModel(**skill_data)
        else:
            # LearnedSkill is a plain SQLAlchemy model (no model_dump); build
            # the export model from its columns explicitly.
            export = SkillExportModel(
                name=skill_data.name,
                namespace=skill_data.namespace or "misc",
                description=skill_data.description or "",
                trigger_patterns=skill_data.trigger_patterns or [],
                parameters=skill_data.parameters or [],
                preconditions=skill_data.preconditions or [],
                instructions=skill_data.instructions,
            )

        base_dir = settings.SKILLS_DIR
        namespace_path = os.path.join(base_dir, export.namespace, export.name)

        ensure_dir(namespace_path)
        skill_md_path = os.path.join(namespace_path, "SKILL.md")

        # 构建 frontmatter
        parameters = [
            p.model_dump() if isinstance(p, BaseModel) else p for p in export.parameters
        ]

        preconditions = [
            p.model_dump() if isinstance(p, BaseModel) else p
            for p in export.preconditions
        ]

        frontmatter = {
            "name": export.name,
            "description": export.description,
            "trigger_patterns": export.trigger_patterns,
            "parameters": parameters,
            "preconditions": preconditions,
        }

        # 生成 Markdown 内容
        content = "---\n"
        content += safe_yaml_dumps(frontmatter)
        content += "---\n\n"

        if export.instructions:
            content += f"## Instructions\n\n{export.instructions}\n\n"

        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Exported physical skill {export.name} to {skill_md_path}")
        return skill_md_path

    except Exception as e:
        logger.exception(f"Failed to export physical skill file: {e}")
        return None


def extract_yaml_block(text: str) -> str | None:
    """
    从文本中提取 YAML 代码块

    支持 ```yaml 和 ``` 两种格式

    Note: Delegates to app.utils.extract.extract_yaml_block for the actual implementation.
    """
    return _extract_yaml_block(text)


def extract_instructions_section(text: str) -> str:
    """
    从 LLM 响应中提取 Markdown 文档部分

    识别 Expert Skill Guide 等标记

    Note: Delegates to app.utils.extract.extract_section for the actual implementation.
    """
    markers = [
        "# 🧠 Expert Skill Guide",
        "# Expert Skill Guide",
        "## 1. Mental Model",
        "## Skill Instructions",
    ]
    return _extract_section(text, markers)


def describe_normalized_position(norm_x: float, norm_y: float) -> str:
    """
    将归一化坐标转换为语义描述

    Returns:
        str: 如 "top-left", "center", "bottom-right"
    """
    # 水平段
    if norm_x < 0.2:
        h = "left"
    elif norm_x < 0.4:
        h = "left-center"
    elif norm_x < 0.6:
        h = "center"
    elif norm_x < 0.8:
        h = "right-center"
    else:
        h = "right"

    # 垂直段
    if norm_y < 0.2:
        v = "top"
    elif norm_y < 0.4:
        v = "upper"
    elif norm_y < 0.6:
        v = "middle"
    elif norm_y < 0.8:
        v = "lower"
    else:
        v = "bottom"

    return f"{v}-{h}"
