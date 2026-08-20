"""Macro execution tool — replays a deterministic macro from the macros table.

宏执行工具：仅处理宏（macro_id / macro_name）。技能（skill）是独立概念，
由技能链路处理；run_macro 不再接受技能参数，语义清晰无混淆。
"""

import logging
from typing import Annotated, Any

from app.core.engine.message.native_classes import RunnableConfig
from app.core.execution.macro import (
    WEB_POLICY,
    MacroEngine,
    find_macro_by_name,
    load_macro,
    resolve_project_base_url,
)
from app.core.hitl import raise_hitl_interrupt
from app.core.hitl.batch_grants import is_operation_granted
from app.core.hitl.prompts import build_approval_context, resolve_tool_context
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.i18n.service import i18n
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


def _resolve_thread_id(config) -> str:
    if not config:
        return "default"
    cfgable = (
        config.get("configurable", {})
        if isinstance(config, dict)
        else getattr(config, "configurable", {})
    )
    return cfgable.get("thread_id", "default") or "default"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.run_macro",
)
async def run_macro(
    macro_id: int | None = None,
    macro_name: str | None = None,
    params: dict[str, Any] | None = None,
    skip_confirmation: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    thread_id = _resolve_thread_id(config)

    if macro_id is None and macro_name is None:
        return ControllerResponse.error(
            "run_macro requires macro_id or macro_name",
            note="Use list_macros to discover available macros.",
        )

    return await _run_macro_row(macro_id, macro_name, params, thread_id, skip_confirmation)


async def _run_macro_row(macro_id, macro_name, params, thread_id, skip_confirmation=False) -> str:
    macro = None
    try:
        if macro_id is not None:
            macro = await load_macro(int(macro_id))
        elif macro_name:
            macro = await find_macro_by_name(macro_name)
    except Exception as e:
        return ControllerResponse.error(
            f"Failed to look up macro '{macro_name or macro_id}'",
            details=str(e),
        )

    if macro is None:
        identifier = f"id={macro_id}" if macro_id else f"name='{macro_name}'"
        return ControllerResponse.not_found(identifier, item_type="macro")

    # 高风险宏确认门控：requires_confirmation=true 的宏必须经运营人员确认后才执行。
    # 豁免（skip_confirmation=True）由 Agent 层控制——运营人员明确授权后由 Agent 传入，
    # 引擎只保证"未确认不得执行"。
    if not skip_confirmation and getattr(macro, "requires_confirmation", False):
        original_args = {"macro_id": macro.id}
        if macro_name:
            original_args["macro_name"] = macro_name
        if params:
            original_args["params"] = params

        # Intent-level batch grant: if this operation is covered by an approved
        # batch grant, execute without per-call confirmation.
        if is_operation_granted(thread_id, "run_macro", params=params, macro_id=macro.id):
            logger.info(
                "[run_macro] Operation covered by batch grant for macro=%s (id=%s), bypassing confirmation.",
                macro.name,
                macro.id,
            )
            skip_confirmation = True

        # If the same macro+params was recently approved, execute directly without
        # asking for confirmation again. The original behavior returned a vague
        # "already approved" message without executing, leaving the Agent uncertain.
        if not skip_confirmation:
            from app.core.hitl.core import find_recently_approved_by_key

            recently_approved = await find_recently_approved_by_key(
                thread_id, "run_macro", original_args
            )
            if recently_approved:
                logger.info(
                    "[run_macro] Recently approved request %s found for macro=%s (id=%s), executing directly.",
                    recently_approved,
                    macro.name,
                    macro.id,
                )
            else:
                return await _request_macro_confirmation(macro, thread_id, original_args)

    execution_params = params.copy() if params else {}
    execution_params["_macro_id"] = macro.id
    execution_params["_macro_name"] = macro.name

    # Inject project url as base_url for {{base_url}} substitutions.
    # Only inject when resolved (None would silently leave {{base_url}}
    # unresolved AND trip the engine's URL guard with a confusing value;
    # routing/actions.py keeps the same guard for L0 path consistency).
    if "base_url" not in execution_params:
        base_url = await resolve_project_base_url(macro.project_id)
        if base_url:
            execution_params["base_url"] = base_url

    logger.info(
        "[run_macro] Executing macro '%s' (id=%s) params=%s",
        macro.name,
        macro.id,
        execution_params,
    )

    result = await MacroEngine.run(
        thread_id,
        macro,
        params=execution_params,
        policy=WEB_POLICY,
    )

    if result.status in ("not_routable", "missing_params", "bad_macro"):
        return ControllerResponse.error(
            f"宏 '{macro.name}' 无法执行: {result.message}",
            note="确认宏已启用（Macro Library），并传入所需参数。",
        )
    detail = _format_macro_result(macro, result)
    if result.success:
        return ControllerResponse.success(f"宏「{macro.name}」执行完成", details=detail or None)
    return ControllerResponse.error(
        f"宏「{macro.name}」执行失败: {result.message}",
        details=detail or None,
    )


def _format_macro_result(macro, result) -> str | None:
    """渲染宏执行的结构化结果摘要（步骤级成败 + 提取数据）。

    解决"宏执行返回空结果"的 Agent 决策黑洞：Agent 拿到各步骤成败与
    提取数据后，可判断宏是真正生效还是跑完没生效（如搜索无结果/页面
    状态未变化），无需再靠外部核验兜底。
    """
    step_log = result.step_log or []
    parts: list[str] = []
    if step_log:
        ok_n = sum(1 for s in step_log if s.get("ok"))
        parts.append(f"步骤 {ok_n}/{len(step_log)} 通过")
        steps_txt = " | ".join(
            f"{s['step']}:{s.get('event_type') or s.get('type')}"
            + ("✓" if s.get("ok") else "✗")
            for s in step_log
        )
        parts.append(f"步骤明细: {steps_txt}")
        fails = [s for s in step_log if not s.get("ok")]
        if fails:
            errs = "; ".join(
                f"第{f['step']}步: {f.get('error', '未生效')}" for f in fails
            )
            parts.append(f"未生效步骤: {errs}")
    if result.extracted_data:
        import json

        parts.append(
            "提取数据: " + json.dumps(result.extracted_data, ensure_ascii=False)
        )
    return "\n".join(parts) if parts else None


async def _request_macro_confirmation(macro, thread_id, original_args: dict) -> str:
    """向运营人员发起宏执行确认（HITL approval），批准后经 resume 链路重执行。

    请求携带 ``authorization`` 元数据（含 ``skip_grant`` 标记）：批准后
    ``resolve_approved_tool_result`` 会用原始参数重执行 run_macro，但不持久化
    授权（宏确认是"每次执行"语义，不写入 project.json authorized_paths）。

    源头去重：同线程下同宏+同参数已有 pending 请求时复用，避免 Agent 重试
    产生重复 approval 请求。
    """
    ctx_fields = resolve_tool_context()
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    action_description = i18n.get(
        "domain_tools.human_input.macro_action", name=macro.name, id=macro.id
    )

    # 展开宏参数到确认信息：运营批准前需看到具体操作对象与值
    # （如改库存：query=片片, new_stock=555），而非仅有宏名。
    # 宏名/参数是业务数据（不翻译），其余文案走 i18n。
    param_lines = []
    _raw_params = (original_args or {}).get("params") or {}
    for k, v in _raw_params.items():
        if k.startswith("_") or k == "base_url":
            continue
        param_lines.append(f"{k}={v}")

    # 填充宏名槽位：宏名如"改库存{query}"中的 {query} 用实际参数替换，
    # 避免运营看到模板占位符（如"改库存{query}"）而非具体商品名。
    macro_name_display = macro.name or ""
    for k, v in _raw_params.items():
        if not k.startswith("_"):
            macro_name_display = macro_name_display.replace("{" + k + "}", str(v))

    action_description = i18n.get(
        "domain_tools.human_input.macro_action",
        name=macro_name_display,
        id=macro.id,
    )
    extra_lines = [
        i18n.get("domain_tools.human_input.macro_confirmation"),
        f"宏：{macro_name_display}",
        f"ID：{macro.id}",
    ]
    if param_lines:
        extra_lines.append(
            i18n.get(
                "domain_tools.human_input.macro_params",
                params="，".join(param_lines),
            )
        )
    extra_lines.append(i18n.get("domain_tools.human_input.macro_confirm_prompt"))

    approval_context = build_approval_context(
        action_description=action_description,
        risk_level=macro.risk_tier or "unknown",
        extra_lines=extra_lines,
    )

    # 源头去重：复用同线程同宏同参数的已有 pending 请求。
    from app.core.hitl.core import (
        _find_pending_by_key,
        find_recently_approved_by_key,
    )

    existing = await _find_pending_by_key(thread_id, "run_macro", original_args)
    if existing:
        logger.info(
            "[run_macro] Reusing existing pending request=%s for macro=%s (id=%s)",
            existing["request_id"],
            macro.name,
            macro.id,
        )
        response_text = (
            f"宏 {macro.name} 已有待确认请求（请求 ID: {existing['request_id']}），"
            "正在等待运营人员确认，已暂停。"
        )
        raise_hitl_interrupt(existing["request_id"], response_text)
        return response_text  # unreachable

    # 循环重试去重：同宏同参数最近已批准（窗口内 completed）时，不再创建新的
    # approval 请求——Supervisor 在批准后若因未收到结束信号反复发起同一宏，
    # 应复用已批准语义，避免对运营轰炸重复确认请求。
    recently_approved = await find_recently_approved_by_key(
        thread_id, "run_macro", original_args
    )
    if recently_approved:
        logger.info(
            "[run_macro] Skipping repeat confirmation for macro=%s (id=%s), "
            "recently approved=%s",
            macro.name,
            macro.id,
            recently_approved,
        )
        return f"宏 {macro.name} 已在请求 {recently_approved} 确认过，不再重复确认。"

    from app.core.hitl.orchestrator import HITLOrchestrator

    response_template = (
        f"高风险宏 {macro.name} 需要运营人员确认后才可执行（请求 ID: {{id}}）。"
        "已暂停等待确认。"
    )
    logger.info(
        "[run_macro] Confirmation requested for macro '%s' (id=%s)",
        macro.name,
        macro.id,
    )
    # 统一发起 approval（create + push + raise），携带 skip_grant（不持久化授权）；
    # resume_override 声明批准后重执行时注入 skip_confirmation 参数，避免死循环。
    return await HITLOrchestrator.raise_approval(
        thread_id=thread_id,
        prompt=action_description,
        context=approval_context,
        tool_name="run_macro",
        risk_level=macro.risk_tier or "high",
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        original_tool_name="run_macro",
        original_tool_args=original_args,
        action="macro_run",
        resource_path=f"macro:{macro.id}",
        skip_grant=True,
        response_template=response_template,
        resume_override={"args": {"skip_confirmation": True}},
    )
