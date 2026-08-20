"""Shared macro utilities (cleanup, verification)."""

from __future__ import annotations

import logging
from typing import Any, cast

from app.constants import DEFAULT_PROJECT_ID
from app.core.execution.macro.schemas import MacroVerificationResult
from app.core.execution.macro.service import MacroService
from app.utils.yaml import macro_from_yaml

logger = logging.getLogger(__name__)


async def verify_macro_script(
    macro_script: list[dict[str, Any]] | str,
    thread_id: str = "verifier",
    _project_id: int = DEFAULT_PROJECT_ID,
    params: dict[str, Any] | None = None,
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
        MacroVerificationResult: 验证结果
    """
    logger.info(f"[{thread_id}] 🔍 Starting macro verification dry-run...")

    try:
        default_params = {"max_scrolls": 2, "is_dry_run": True}
        if params:
            default_params.update(params)

        # dry-run 与真实执行对齐：注入 {{base_url}}，否则 navigate 步骤的
        # 占位符/相对路径直接进 page.goto → "Cannot navigate to invalid URL"，
        # 导致 Agent 造宏验证必败且报错无细节。
        if "base_url" not in default_params and _project_id:
            from app.core.execution.macro.runner import resolve_project_base_url

            base_url = await resolve_project_base_url(_project_id)
            if base_url:
                default_params["base_url"] = base_url

        if isinstance(macro_script, str):
            steps: list[dict[str, Any]] = macro_from_yaml(macro_script)
        elif isinstance(macro_script, list):
            steps = macro_script
        else:
            return MacroVerificationResult(
                status="error",
                success=False,
                error="macro_script must be a list of steps or a YAML string",
            )

        result = cast(
            dict[str, Any],
            await MacroService.run(
                thread_id=thread_id,
                script_input=steps,
                params=default_params
            )
        )

        success = result.get("success", False)
        extracted_data = result.get("extracted_data") or {}
        step_log = result.get("step_log")

        expected_keys = [s["key"] for s in steps if s.get("type") == "extract"]
        missing_keys = [k for k in expected_keys if k not in extracted_data]

        status = "success" if success and not missing_keys else "failed"

        logger.info(
            f"[{thread_id}] Verification {status}. "
            f"Extracted keys: {list(extracted_data.keys())}"
        )

        # MacroRunResult 只有 message 字段（无 error）；之前只读 error 导致
        # 真实失败原因（如 "Cannot navigate to invalid URL"）被吞成空，
        # Agent 只看到 "Macro verification failed: failed" 无细节。
        # 仅在失败时回退到 message（成功时的 message 不是错误）。
        error = result.get("error")
        if error is None and not success:
            error = result.get("message")

        # 失败时把步骤级执行记录（step_log）编译成可诊断摘要，随 error 一起
        # 返回，否则 Agent 只能看到 "failed" 无法定位出错步骤。
        if not success and step_log:
            failed_steps = [s for s in step_log if not s.get("ok")]
            if failed_steps:
                detail = "; ".join(
                    f"step {s.get('step')}({s.get('type')}/{s.get('event_type', '-')}): "
                    f"{s.get('error') or 'failed'}"
                    for s in failed_steps[:5]
                )
                error = f"{error or 'Macro verification failed'}; failed steps: {detail}"
            else:
                error = f"{error or 'Macro verification failed'}; step_log: {step_log[:10]}"

        return MacroVerificationResult(
            status=status,
            success=success,
            missing_keys=missing_keys,
            extracted_count=len(extracted_data),
            error=error,
            step_log=step_log,
        )
    except Exception:
        logger.exception("[%s] Macro verification crashed", thread_id)
        return MacroVerificationResult(status="error", success=False, error="verification crashed")


def cleanup_macro_steps(
    steps: list[dict[str, Any]],
    start_index: int = 1
) -> tuple[list[dict[str, Any]], int]:
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
