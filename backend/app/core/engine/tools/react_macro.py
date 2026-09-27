"""React engine `macro` tool — single unified macro entry (OpenCode `tool/task.ts` §5.7).

把 宏的增删改查/执行/查看 收敛为单一 ``macro`` 工具，按 ``action`` 分发，与
``skill``（索引+按需加载）对齐：索引 + 查看 + 执行 + 编写
全在一个工具内完成。实际执行/编写仍复用既有的确定性回放（run_macro）与 authoring
校验管线（create_macro/update_macro），此处只做薄分发。

Actions:
- list:   列出可用宏（等价于 <available_macros> 发现）。
- read:   查看宏的完整元数据与脚本（含 risk_tier/参数/完整 YAML，原名 load 的增强版）。
- run:    执行一个宏（含高风险宏确认门控，对应 run_macro）。
- create: 编写宏——script_steps 显式编写（经 authoring 校验门）或由当前会话 trace 回放编译。
- update: 更新宏元数据或（在通过校验门后）重写脚本。
- delete: 删除一个宏。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.hitl.authorization import AuthorizationService
from app.core.hitl.core import hitl_enabled, raise_hitl_interrupt
from app.core.hitl.prompts import build_approval_context, resolve_tool_context
from app.core.learning.macro import (
    WEB_POLICY,
    MacroEngine,
    find_macro_by_name,
    load_macro,
    resolve_project_base_url,
)
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.i18n.service import i18n
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=False,
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.macro",
)
async def macro(
    action: Literal["list", "read", "run", "create", "update", "delete", "debug"] = "list",
    name: str | None = None,
    macro_id: int | None = None,
    params: dict[str, Any] | None = None,
    skip_confirmation: bool = False,
    description: str | None = None,
    trigger_patterns: list[str] | None = None,
    script_steps: list[dict[str, Any]] | None = None,
    parameters: list[dict] | None = None,
    macro_script: str | None = None,
    rationale: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一宏入口——在一个调用里完成宏的 list / read / debug / run / create / update / delete。

    宏 = 可复用的确定性 UI 自动化脚本（YAML 步骤列表，三端：浏览器/桌面/移动），把重复操作
    变成一句话命令（如「抓取每日订单」）。用户要"录成宏/以后叫名字执行/每天自动做 XX"→
    create 落库 + run 验证真实采到数据才算完成，只写脚本文件是半成品。

    Actions:
    - list/read: 列已激活宏库 / 看某宏完整元数据+YAML（name 或 macro_id）。
    - run: 执行宏（高风险需确认；name/macro_id + 可选 params）。
    - create: script_steps（MacroStep dict 列表）+ rationale 手写；或不传 script_steps
      从本会话已完成操作 trace 回放编译。
    - debug: script_steps 或 macro_script(YAML) 试跑，不落库，返回逐步成败——
      正式 create 前先用它跑通。
    - update/delete: 改名/描述/参数（重写脚本须 rationale 且过校验门）/按 macro_id 删除。

    MacroStep 核心格式：type=action|extract|control|if|loop；event_type=click/input/wait/
    navigate/open_app/get_text 等；payload 为动作参数（navigate 的 url 必须绝对地址或
    {{base_url}} 占位符）；step_number 整数递增。
    写宏完整工作流（探索→打样→debug→create→run）与 DSL 全量枚举/三端细则，以
    skill(name="Macro Authoring Guide") 为准，动手前先加载它。
    """
    _t = _resolve_thread_id(config)

    if action == "list":
        return await _macro_list(project_id=_project_id())

    if action == "read":
        return await _macro_read(
            name=name, macro_id=macro_id, project_id=_project_id()
        )

    if action == "run":
        if macro_id is None and name is None:
            return _err(
                "macro run 需要 macro_id 或 name",
                "先 list 查看可用宏。",
            )
        return await _macro_run(
            macro_id=macro_id,
            name=name,
            params=params,
            thread_id=_t,
            skip_confirmation=skip_confirmation,
            project_id=_project_id(),
        )

    if action == "create":
        return await _macro_create(
            name=name, description=description,
            trigger_patterns=trigger_patterns, script_steps=script_steps,
            parameters=parameters, rationale=rationale,
        )

    if action == "update":
        if macro_id is None:
            return _err("macro update 需要 macro_id", None)
        return await _macro_update(
            macro_id=macro_id, name=name, description=description,
            trigger_patterns=trigger_patterns, parameters=parameters,
            macro_script=macro_script, rationale=rationale,
            project_id=_project_id(),
        )

    if action == "delete":
        if macro_id is None:
            return _err("macro delete 需要 macro_id", None)
        if not rationale:
            return _err("macro delete 需要 rationale（说明删除原因）", None)
        return await _macro_delete(
            macro_id=macro_id, rationale=rationale, project_id=_project_id()
        )

    if action == "debug":
        if script_steps is None and macro_script is None:
            return _err(
                "macro debug 需要 script_steps（步骤 dict 列表）或 macro_script（YAML 字符串）",
                "调试不落库：走风险门后完整执行一遍，返回 step_log 与提取数据。",
            )
        return await _macro_debug(
            script_steps=script_steps,
            macro_script=macro_script,
            params=params,
            thread_id=_t,
        )

    return f"Error: unknown macro action '{action}'."


def _resolve_thread_id(config) -> str:
    if not config:
        return "default"
    cfgable = (
        config.get("configurable", {})
        if isinstance(config, dict)
        else getattr(config, "configurable", {})
    )
    return cfgable.get("thread_id", "default") or "default"


def _err(message: str, note: str | None) -> str:
    from app.utils.controller_response import ControllerResponse

    return ControllerResponse.error(message, note=note)


def _project_id() -> int:
    from app.constants import DEFAULT_PROJECT_ID
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    return ctx.project_id if ctx else DEFAULT_PROJECT_ID


def _member_id() -> int:
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    return ctx.member_id if ctx else 0


def _thread_id() -> str | None:
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    return ctx.thread_id if ctx else None


async def _macro_list(*, project_id: int | None = None) -> str:
    from app.core.learning.macro.lifecycle import list_macros

    try:
        macros = await list_macros(
            project_id=project_id,
            status="verified",
            is_active=True,
            limit=50,
        )
    except Exception as e:  # noqa: BLE001 - 列表失败容错返回可读信息
        logger.exception(f"[MacroTool] list failed: {e}")
        return f"Error: failed to list macros: {e}"

    if not macros:
        return "当前没有可用宏（已按当前项目过滤）。"

    lines = [f"# 可用宏（{len(macros)}）"]
    for m in macros:
        lines.append(
            f"- {m.name} (id={getattr(m, 'id', '?')})"
            f"{': ' + m.description if getattr(m, 'description', None) else ''}"
        )
    if len(macros) >= 50:
        lines.append("\n（最多显示 50 条，用宏观面进一步筛选）")
    return "\n".join(lines)


async def _macro_read(
    *, name: str | None, macro_id: int | None, project_id: int | None
) -> str:
    from app.core.learning.macro import find_macro_by_name, load_macro

    try:
        if macro_id is not None:
            found = await load_macro(int(macro_id), project_id=project_id)
        elif name:
            found = await find_macro_by_name(name, project_id=project_id)
        else:
            found = None
    except Exception as e:
        logger.exception(f"[MacroTool] read lookup failed: {e}")
        return f"Error: failed to look up macro '{name or macro_id}': {e}"

    if not found:
        return _err(
            f"macro '{name or macro_id}' 不存在",
            "先 list 查看可用宏，不要臆造名称。",
        )

    lines = [
        f"# Macro #{found.id}: {found.name}",
        f"  Description: {found.description or '(no description)'}",
        f"  Status: {found.status}",
        f"  Active: {found.is_active}",
        f"  Risk tier: {found.risk_tier}",
        f"  Requires confirmation: {found.requires_confirmation}",
        f"  Allow self-healing: {found.allow_self_healing}",
        f"  Trigger patterns: {found.trigger_patterns or []}",
        f"  Parameters: {found.parameters or []}",
        "",
        "Script:",
        found.macro_script or "（无 macro_script 内容）",
    ]
    return "\n".join(lines)


async def _macro_run(
    *,
    macro_id: int | None,
    name: str | None,
    params: dict[str, Any] | None,
    thread_id: str,
    skip_confirmation: bool,
    project_id: int | None,
) -> str:
    return await _run_macro_row(
        macro_id=macro_id,
        macro_name=name,
        params=params,
        thread_id=thread_id,
        skip_confirmation=skip_confirmation,
        project_id=project_id,
    )


async def _macro_create(
    *,
    name: str | None,
    description: str | None,
    trigger_patterns: list[str] | None,
    script_steps: list[dict[str, Any]] | None,
    parameters: list[dict] | None,
    rationale: str | None,
) -> str:
    from app.core.context.manager import ContextManager

    if not name:
        return _err("macro create 需要 name", None)
    if script_steps is not None and not rationale:
        return _err(
            "提供 script_steps 时必须给 rationale（说明为何创建该宏）", None
        )

    ctx = ContextManager.current()
    target_thread = ctx.thread_id if ctx else None
    project_id = ctx.project_id if ctx else 0
    member_id = ctx.member_id if ctx else 0

    if script_steps is None:
        return await _create_macro_from_trace(
            target_thread or "default",
            name, description or "", trigger_patterns, member_id,
        )
    return await _create_macro_from_script(
        target_thread=target_thread or "default",
        project_id=project_id,
        member_id=member_id,
        name=name,
        description=description or "",
        trigger_patterns=trigger_patterns,
        script_steps=script_steps,
        parameters=parameters,
        rationale=rationale,
    )


async def _macro_debug(
    *,
    script_steps: list[dict[str, Any]] | None,
    macro_script: str | None,
    params: dict[str, Any] | None,
    thread_id: str,
) -> str:
    """调试执行一个宏脚本，不落库。

    用途：在正式 ``macro create`` 之前，快速验证/调试一段脚本能否跑通——
    直接执行并返回逐步成败与提取数据，方便 agent 定位哪一步失败。等同
    于 create 的校验门，但不创建任何宏记录。
    """
    from app.core.learning.constants import DEFAULT_ALLOWED_FAMILIES  # noqa: E402
    from app.core.learning.macro.schemas import (
        MacroScript,
        compute_max_risk,
        scan_step_families,
    )
    from app.core.learning.macro.service import MacroService
    from app.core.learning.macro.utils import cleanup_macro_steps
    from app.utils.yaml import macro_from_yaml

    try:
        if macro_script is not None:
            raw_steps = macro_from_yaml(macro_script)
        else:
            raw_steps = script_steps or []
    except Exception as e:
        return f"Error: Invalid macro script: {e}"

    try:
        cleaned_steps, _ = cleanup_macro_steps(raw_steps)
        script = MacroScript(steps=cleaned_steps)
    except Exception as e:
        return f"Error: Invalid macro script: {e}"

    reason = scan_step_families(script.steps, DEFAULT_ALLOWED_FAMILIES)
    if reason:
        return f"Error: Risk gate rejected: {reason}"

    result = await MacroService.run(thread_id=thread_id, script_input=script, params=params or {})

    max_risk = compute_max_risk(script.steps)
    lines = [f"# Debug run: risk_tier={max_risk} status={result.status or ('ok' if result.success else 'fail')}"]
    step_log = result.step_log or []
    if step_log:
        ok_n = sum(1 for s in step_log if s.get("ok"))
        lines.append(f"步骤 {ok_n}/{len(step_log)} 通过")
        lines.append("步骤明细: " + " | ".join(
            f"{s['step']}:{s.get('event_type') or s.get('type')}"
            + ("✓" if s.get("ok") else "✗")
            for s in step_log
        ))
        fails = [s for s in step_log if not s.get("ok")]
        if fails:
            errs = "; ".join(f"第{f['step']}步: {f.get('error', '未生效')}" for f in fails)
            lines.append(f"未生效步骤: {errs}")
    if result.extracted_data:
        import json

        lines.append("提取数据: " + json.dumps(result.extracted_data, ensure_ascii=False)[:2000])
    if not result.success and result.message:
        lines.append(f"结果: {result.message}")
    return "\n".join(lines)


async def _macro_update(
    *,
    macro_id: int,
    name: str | None,
    description: str | None,
    trigger_patterns: list[str] | None,
    parameters: list[dict] | None,
    macro_script: str | None,
    rationale: str | None,
    project_id: int | None,
) -> str:
    from app.core.learning.macro import (
        confirm_macro,
        downgrade_macro,
        load_macro,
    )
    from app.core.learning.macro import update_macro as lifecycle_update_macro
    from app.utils.parameters import finalize_macro_parameters

    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if trigger_patterns is not None:
        fields["trigger_patterns"] = trigger_patterns
    if parameters is not None:
        fields["parameters"] = parameters

    if macro_script is not None:
        if not rationale:
            return _err(
                "重写宏脚本时必须给 rationale",
                "说明原脚本哪里不对、新脚本如何修复。",
            )
        try:
            macro = await load_macro(int(macro_id), project_id=project_id)
            if macro is None:
                return _err(f"Macro #{macro_id} 不存在（或不属于当前项目）", None)
        except Exception as e:
            logger.exception(f"[MacroTool] load for update failed: {e}")
            return f"Error: failed to load macro: {e}"

        validation = await _verify_new_script(macro_id, macro.project_id, macro_script)
        if not validation.ok:
            return _err(validation.error, None)
        fields["macro_script"] = macro_script
        fields["risk_tier"] = validation.max_risk
        fields["requires_confirmation"] = validation.requires_confirmation
        fields["allow_self_healing"] = True
        if "parameters" not in fields:
            fields["parameters"] = finalize_macro_parameters(None, macro_script)

    if not fields:
        return _err(
            "没有可更新的字段",
            "至少提供 name / description / trigger_patterns / parameters / macro_script 之一。",
        )

    try:
        if "macro_script" not in fields:
            existing = await load_macro(int(macro_id), project_id=project_id)
            if existing is None:
                return _err(f"Macro #{macro_id} 不存在（或不属于当前项目）", None)
        ok = await lifecycle_update_macro(int(macro_id), fields)
        if not ok:
            return _err(f"Failed to update macro #{macro_id}.", None)
        script_note = ""
        if "macro_script" in fields:
            await downgrade_macro(int(macro_id))
            confirmed = await confirm_macro(int(macro_id))
            script_note = (
                " 新脚本已真实执行校验并重新激活。"
                if confirmed
                else " 重写后激活失败；宏未激活——需上报。"
            )
        updated = ", ".join(fields.keys())
        return f"Macro #{macro_id} 已更新 ({updated})." + script_note
    except Exception as e:
        logger.exception(f"[MacroTool] update failed: {e}")
        return _err(f"Failed to update macro: {e}", None)


async def _verify_new_script(macro_id: int, project_id: int, macro_script: str):
    from app.core.learning.macro.authoring import validate_script

    return await validate_script(macro_script, thread_id=f"rewrite-{macro_id}", project_id=project_id)


async def _macro_delete(*, macro_id: int, rationale: str, project_id: int | None) -> str:
    from app.core.learning.macro import delete_macro as lifecycle_delete_macro
    from app.core.learning.macro import load_macro

    try:
        macro = await load_macro(int(macro_id), project_id=project_id)
        if macro is None:
            return _err(f"Macro #{macro_id} not found (或不属于当前项目).", None)
        ok = await lifecycle_delete_macro(int(macro_id))
        if not ok:
            return _err(f"Failed to delete macro #{macro_id}.", None)
        logger.info("Agent deleted macro #%s: %s (rationale: %s)", macro_id, macro.name, rationale)
        return f"Macro #{macro_id} ({macro.name}) 已删除。Rationale: {rationale}"
    except Exception as e:
        logger.exception(f"[MacroTool] delete failed: {e}")
        return _err(f"Failed to delete macro: {e}", None)


# ---------------------------------------------------------------------------
# 宏执行与创建的实现层（原 run_macro / create_macro 独立工具的实现体，随工具
# 退役并入 facade——react_macro 是它们唯一的消费者）。HITL 账本键 "run_macro"
# 为历史授权域字符串，保持不变以维持 grant/去重语义。
# ---------------------------------------------------------------------------


async def _run_macro_row(
    macro_id, macro_name, params, thread_id, skip_confirmation=False, project_id=None
) -> str:
    macro = None
    try:
        if macro_id is not None:
            macro = await load_macro(int(macro_id), project_id=project_id)
        elif macro_name:
            macro = await find_macro_by_name(macro_name, project_id=project_id)
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
        # EXECUTION_MODE=docker：无人值守流水线不发起宏确认 HITL，
        # 视为自动批准（沙箱隔离兜底）。
        if not hitl_enabled():
            logger.info(
                "[run_macro] docker mode: auto-approving confirmation for macro=%s (id=%s)",
                macro.name,
                macro.id,
            )
            skip_confirmation = True
        else:
            original_args = {"macro_id": macro.id}
            if macro_name:
                original_args["macro_name"] = macro_name
            if params:
                original_args["params"] = params

            # 宏粒度"总是允许"（grant_mode=always 写盘的持久化授权）：命中即短路确认。
            if await AuthorizationService(macro.project_id).is_granted(
                f"macro:{macro.id}", "macro_run"
            ):
                logger.info(
                    "[run_macro] Macro permanently granted for macro=%s (id=%s), bypassing confirmation.",
                    macro.name,
                    macro.id,
                )
                skip_confirmation = True

            # If the same macro+params was recently approved, execute directly without
            # asking for confirmation again.
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
                    return await _request_macro_confirmation(
                        macro, thread_id, original_args
                    )

    execution_params = params.copy() if params else {}
    execution_params["macro_id"] = macro.id
    execution_params["macro_name"] = macro.name

    # Inject project url as base_url for {{base_url}} substitutions.
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
        return ControllerResponse.success(
            f"宏「{macro.name}」执行完成", details=detail or None
        )
    return ControllerResponse.error(
        f"宏「{macro.name}」执行失败: {result.message}",
        details=detail or None,
    )


def _format_macro_result(macro, result) -> str | None:  # noqa: ARG001
    """渲染宏执行的结构化结果摘要（步骤级成败 + 提取数据）。"""
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
    """向运营人员发起宏执行确认（HITL approval），批准后经 resume 链路重执行。"""
    ctx_fields = resolve_tool_context()
    project_id = macro.project_id
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    param_lines = []
    _raw_params = (original_args or {}).get("params") or {}
    for k, v in _raw_params.items():
        if k.startswith("_") or k == "base_url":
            continue
        param_lines.append(f"{k}={v}")

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
                "domain_tools.human_input.macro_params", params="，".join(param_lines)
            )
        )
    extra_lines.append(i18n.get("domain_tools.human_input.macro_confirm_prompt"))

    approval_context = build_approval_context(
        action_description=action_description,
        risk_level=macro.risk_tier or "unknown",
        extra_lines=extra_lines,
    )

    # 源头去重：复用同线程同宏同参数的已有 pending 请求。
    from app.core.hitl.core import _find_pending_by_key, find_recently_approved_by_key

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
    # approval 请求。
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
        response_template=response_template,
        resume_override={"args": {"skip_confirmation": True}},
    )


async def _create_macro_from_trace(
    target_thread: str,
    name: str,
    description: str,
    trigger_patterns: list[str] | None,
    member_id: int,
) -> str:
    """Trace-to-macro path：回放会话已完成的真实操作编译宏。"""
    from app.core.learning.macro import MacroCreatorService, confirm_macro
    from app.infrastructure.database import session_scope

    try:
        is_eligible = await MacroCreatorService.is_eligible(target_thread)
        if not is_eligible:
            return (
                "This thread does not contain replayable UI actions "
                "(e.g., clicks, taps, inputs). Macro creation requires "
                "a trace with at least 2 replayable steps. Please complete "
                "the task first, then try again."
            )

        macro = await MacroCreatorService.create_macro_from_trace(
            thread_id=target_thread,
            member_id=member_id,
            name=name,
            description=description,
            trigger_patterns=trigger_patterns,
        )

        if macro is None:
            return (
                "Macro creation completed but no macro was created. "
                "The trace may not contain enough actionable steps."
            )

        macro_id = macro.id if hasattr(macro, "id") else macro.get("id")

        async with session_scope() as db:
            confirmed = await confirm_macro(int(macro_id), db=db)

        status_note = (
            "Verification passed; the macro is active and discoverable via the macro list."
            if confirmed
            else "Activation failed; the macro remains inactive — report this to the user."
        )
        return (
            f"✅ Macro created from trace (ID: {macro_id}, name: {name}). {status_note}"
        )
    except Exception as e:
        logger.exception(f"Failed to create macro from trace: {e}")
        return f"Error: Failed to create macro from trace: {str(e)}"


async def _create_macro_from_script(
    target_thread: str,
    project_id: int,
    member_id: int,
    name: str,
    description: str,
    trigger_patterns: list[str] | None,
    script_steps: list[dict[str, Any]],
    parameters: list[dict] | None = None,
    rationale: str | None = None,
) -> str:
    """Agent-written macro path: validate, gate, real-execute, persist."""
    try:
        from app.core.learning.macro.authoring import validate_script
        from app.core.learning.macro.lifecycle import (
            confirm_macro,
            create_macro_from_synthesis,
        )
        from app.core.learning.macro.schemas import MacroScript
        from app.infrastructure.database import session_scope
        from app.utils.parameters import finalize_macro_parameters

        validation = await validate_script(
            script_steps, thread_id=target_thread, project_id=project_id
        )
        if not validation.ok:
            return f"Error: {validation.error}"

        max_risk = validation.max_risk
        requires_confirmation = validation.requires_confirmation

        final_params = finalize_macro_parameters(
            parameters, MacroScript(steps=validation.cleaned_steps).to_yaml()
        )

        async with session_scope() as db:
            existing = await find_macro_by_name(name, project_id=project_id, db=db)
            if existing is not None:
                return (
                    f"Error: A macro named '{name}' already exists (id={existing.id})."
                )

            macro = await create_macro_from_synthesis(
                db,
                name=name,
                description=description,
                trigger_patterns=trigger_patterns or [],
                parameters=final_params,
                macro_script=MacroScript(steps=validation.cleaned_steps).to_yaml(),
                risk_tier=max_risk,
                requires_confirmation=requires_confirmation,
                source_thread_id=target_thread,
                project_id=project_id,
                member_id=member_id,
            )
            macro_id = macro.id

        logger.info(
            "[MacroTool] Agent-written macro created: id=%s name=%s risk=%s "
            "requires_confirmation=%s rationale=%r",
            macro_id,
            name,
            max_risk,
            requires_confirmation,
            rationale,
        )

        async with session_scope() as db:
            confirmed = await confirm_macro(macro_id, db=db)

        if not confirmed:
            logger.warning(
                "[MacroTool] Agent-written macro %s failed self-activation; "
                "it remains inactive.",
                macro_id,
            )
            return (
                f"⚠️ Macro created (ID: {macro_id}, name: {name}) and verified by "
                f"real execution, but activation failed. Report the macro ID to the "
                f"user; it is not discoverable yet."
            )

        return (
            f"✅ Macro created and self-verified (ID: {macro_id}, name: {name}, "
            f"risk={max_risk}). Real-execution verification passed and the macro is "
            f"now active and discoverable via the macro list."
        )
    except Exception as e:
        logger.exception(f"Failed to create macro from script: {e}")
        return f"Error: Failed to create macro from script: {str(e)}"
