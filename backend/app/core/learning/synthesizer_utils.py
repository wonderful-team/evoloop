"""
Skill Synthesizer 共享工具函数

提取 WorkflowSynthesizer 和 MultimodalSkillSynthesizer 的重复逻辑，
避免代码重复，提高可维护性。
"""

import logging
import os
from typing import Any

import yaml
from pydantic import Field

from app.core.config import settings
from app.core.file import ensure_dir
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.extract import extract_section as _extract_section
from app.utils.extract import extract_yaml_block as _extract_yaml_block
from app.utils.time import normalize_timestamp_ms_to_sec as _normalize_timestamp

logger = logging.getLogger(__name__)


class SkillExportModel(DynamicBaseModel):
    name: str
    namespace: str = "misc"
    description: str = ""
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[Any] = Field(default_factory=list)
    preconditions: list[Any] = Field(default_factory=list)
    instructions: str | None = None


def export_skill_to_filesystem(skill_data: Any) -> str | None:
    """
    导出技能到文件系统 (SKILL.md)
    """
    try:
        # Convert to a standard export model to avoid getattr/Any mess
        if not isinstance(skill_data, dict):
            # Try model_dump if it's a Pydantic model
            if hasattr(skill_data, "model_dump"):
                data = skill_data.model_dump()
            else:
                # Fallback for other objects
                data = {
                    "name": skill_data.name,
                    "namespace": skill_data.namespace or "misc",
                    "description": skill_data.description,
                    "trigger_patterns": skill_data.trigger_patterns or [],
                    "parameters": skill_data.parameters or [],
                    "preconditions": skill_data.preconditions or [],
                    "instructions": skill_data.instructions,
                }
        else:
            data = skill_data

        export = SkillExportModel(**data)

        base_dir = settings.SKILLS_DIR
        namespace_path = os.path.join(base_dir, export.namespace, export.name)

        ensure_dir(namespace_path)
        skill_md_path = os.path.join(namespace_path, "SKILL.md")

        # 构建 frontmatter
        parameters = []
        for p in export.parameters:
            parameters.append(p.model_dump() if hasattr(p, "model_dump") else p)

        preconditions = []
        for p in export.preconditions:
            preconditions.append(p.model_dump() if hasattr(p, "model_dump") else p)

        frontmatter = {
            "name": export.name,
            "description": export.description,
            "trigger_patterns": export.trigger_patterns,
            "parameters": parameters,
            "preconditions": preconditions,
        }

        # 生成 Markdown 内容
        content = "---\n"
        content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        content += "---\n\n"

        if export.instructions:
            content += f"## Instructions\n\n{export.instructions}\n\n"

        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Exported physical skill {export.name} to {skill_md_path}")
        return skill_md_path

    except Exception as e:
        logger.error(f"Failed to export physical skill file: {e}")
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
        "## Skill Instructions"
    ]
    return _extract_section(text, markers)


def normalize_timestamp_to_seconds(timestamp: float) -> float:
    """
    将相对毫秒时间戳转换为秒

    所有录制源（Android/DOM/Global）都统一使用相对毫秒时间戳，
    即相对于视频录制开始的毫秒数。

    Args:
        timestamp: 相对毫秒时间戳（从视频开始计算的毫秒数）

    Returns:
        float: 相对秒数（从视频开始计算的秒数）
    
    Note: Delegates to app.utils.time.normalize_timestamp_ms_to_sec for the actual implementation.
    """
    return _normalize_timestamp(timestamp)


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
