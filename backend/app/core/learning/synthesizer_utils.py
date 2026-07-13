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

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.file import ensure_dir
from app.core.learning.schemas import MacroVerificationResult
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.extract import extract_section as _extract_section
from app.utils.extract import extract_yaml_block as _extract_yaml_block
from app.utils.time import normalize_timestamp_ms_to_sec as _normalize_timestamp

logger = logging.getLogger(__name__)


async def verify_macro_script(
    macro_script: list[dict] | str,
    thread_id: str = "verifier",
    project_id: int = DEFAULT_PROJECT_ID,
    params: dict | None = None
) -> MacroVerificationResult:
    """
    统一宏脚本验证函数

    执行宏脚本的 Dry-run 验证，检查提取目标是否达成。

    Args:
        macro_script: 宏脚本步骤列表 (list) 或 YAML 字符串
        thread_id: 验证线程标识（用于日志）
        project_id: 项目ID
        params: 可选的运行参数（如 {"max_scrolls": 2, "is_dry_run": True}）

    Returns:
        dict: 验证结果
        {
            "status": "success" | "failed" | "error",
            "success": bool,
            "missing_keys": list[str],
            "extracted_count": int,
            "error": str | None
        }
    """
    from app.core.execution.macro.service import MacroService

    logger.info(f"[{thread_id}] 🔍 Starting macro verification dry-run...")

    try:
        default_params = {"max_scrolls": 2, "is_dry_run": True}
        if params:
            default_params.update(params)

        # Parse YAML string input first — MacroService.run accepts a
        # MacroScript object or a list of step dicts, never a raw string.
        steps = macro_script
        if isinstance(macro_script, str):
            from app.utils.yaml import macro_from_yaml
            steps = macro_from_yaml(macro_script)

        result = await MacroService.run(
            thread_id=thread_id,
            script_input=steps,
            params=default_params
        )

        success = result.get("success", False)
        # MacroService.run leaves extracted_data=None on failure paths; `.get`
        # with a default only covers a missing key, not a None value.
        extracted_data = result.get("extracted_data") or {}

        expected_keys = [s["key"] for s in steps if s.get("type") == "extract"]
        missing_keys = [k for k in expected_keys if k not in extracted_data]

        status = "success" if success and not missing_keys else "failed"

        logger.info(
            f"[{thread_id}] Verification {status}. "
            f"Extracted keys: {list(extracted_data.keys())}"
        )

        return MacroVerificationResult(
            status=status,
            success=success,
            missing_keys=missing_keys,
            extracted_count=len(extracted_data),
            error=result.get("error")
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.error(f"[{thread_id}] Macro verification crashed: {e}")
        return MacroVerificationResult(
            status="error",
            success=False,
            error=str(e)
        )


def cleanup_macro_steps(
    steps: list[dict],
    start_index: int = 1
) -> tuple[list[dict], int]:
    """
    规范化宏步骤

    修复常见格式错误并确保全局步骤编号唯一。
    处理嵌套步骤（if/while 等控制流的 then_steps/else_steps/steps）。

    Args:
        steps: 原始宏步骤列表
        start_index: 起始步骤编号

    Returns:
        Tuple[规范化后的步骤列表, 下一个可用索引]
    """
    clean_steps = []
    current_idx = start_index

    for step in steps:
        if not isinstance(step, dict):
            continue

        step["step_number"] = current_idx
        current_idx += 1

        s_type = step.get("type")
        if s_type == "wait":
            step["type"] = "action"
            step["event_type"] = "wait"
            payload = step.get("payload", {})
            if "timeout" in step and "seconds" not in payload:
                payload["seconds"] = float(step["timeout"]) / 1000.0
            step["payload"] = payload
        elif s_type in ("while", "batch_loop", "loop"):
            step["type"] = "loop"

        # 规范化嵌套字段名
        if "then" in step and "then_steps" not in step:
            step["then_steps"] = step.pop("then")
        if "else" in step and "else_steps" not in step:
            step["else_steps"] = step.pop("else")
        legacy_substeps = step.pop("do", None) or step.pop("do_steps", None)
        if legacy_substeps and "steps" not in step:
            step["steps"] = legacy_substeps

        # 递归处理嵌套步骤，共享计数器
        for branch in ["then_steps", "else_steps", "steps"]:
            if branch in step and isinstance(step[branch], list):
                nested_steps, next_idx = cleanup_macro_steps(
                    step[branch], start_index=current_idx
                )
                step[branch] = nested_steps
                current_idx = next_idx

        clean_steps.append(step)

    return clean_steps, current_idx


class SkillExportModel(DynamicBaseModel):
    name: str
    namespace: str = "misc"
    description: str = ""
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[Any] = Field(default_factory=list)
    preconditions: list[Any] = Field(default_factory=list)
    instructions: str | None = None
    macro_script: str | None = None


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
                    "macro_script": None,
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

        if export.macro_script:
            content += "## Macro Script\n\n"
            content += "```yaml\n"
            content += export.macro_script
            content += "\n```\n"

        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Exported physical skill {export.name} to {skill_md_path}")
        return skill_md_path

    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
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
