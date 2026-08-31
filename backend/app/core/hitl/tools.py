"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.

This module is a thin wrapper around app.core.hitl; the shared HITL primitives
live there so they can also be used by the authorization framework.
"""

import logging

from app.core.hitl.core import (
    auto_hitl_response,
    create_request,
    hitl_enabled,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.core.hitl.prompts import build_approval_context, resolve_tool_context
from app.core.hitl.schemas import RequestApprovalArgs, RequestHumanInputArgs
from app.core.hitl.types import HITLDecision, HumanRequestType, RiskLevel
from app.core.tools import evoloop_tool
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


# ============ Tools ============


@evoloop_tool(
    name="question",
    args_schema=RequestHumanInputArgs,
    is_hitl=True,
    summary_template="evoloop.tool_summary.ask_user",
    handle_tool_error=False,  # HITL must propagate interrupt exception
)
async def ask_human(
    prompt: str,
    input_type: HumanRequestType = HumanRequestType.TEXT,
    options: list[str] | None = None,
    context: str | None = None,
    default_value: str | None = None,
) -> str:
    """
    暂停执行，向用户请求输入。

    在以下情况使用本工具：
    - 需要只有用户才能提供的信息
    - 需要澄清需求
    - 需要用户在多个选项间做决定
    - 需要在继续前获得确认

    **批量勾选处理范围（重要）**：当需要运营从多个同类待办中**挑选一部分**处理时
    （例如多笔退款/提现中只处理其中几笔），使用 ``input_type="multi_choice"``，
    在 ``options`` 中列出可勾选项（可给出"全部处理 / 仅处理某类 / 各单据编号"等）。
    运营可勾选多项，返回值是**逗号分隔的选中清单**；随后只执行清单内的项。
    不要为每一笔单独请求确认。

    流程会暂停直到用户响应。

    返回用户响应字符串。
    """
    # EXECUTION_MODE=docker：无人值守流水线不挂起，走自动应答（沙箱隔离兜底）。
    if not hitl_enabled():
        answer = auto_hitl_response(
            input_type, default_value=default_value, options=options
        )
        logger.info(
            "[HITL] docker mode: ask_human auto-answered type=%s (sandbox isolation)",
            input_type,
        )
        return answer

    ctx_fields = resolve_tool_context()
    thread_id = ctx_fields["thread_id"]
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    # input_type 是 HumanRequestType 枚举，其值即标准 request_type
    # （与 HumanRequestType 枚举值一致），直接透传给 create_request 校验。

    # Validate choice options
    if input_type in ("choice", "multi_choice") and not options:
        return i18n.get("domain_tools.human_input.error_options")

    # Create the request
    request = await create_request(
        thread_id=thread_id,
        request_type=input_type,
        prompt=prompt,
        options=options,
        context=context,
        default_value=default_value,
    )

    # Format response for the agent
    context_section = ""
    if context:
        context_section = f"\n{i18n.get('domain_tools.human_input.context', context={'context': context})}"

    options_section = ""
    if options:
        options_section = f"\n{i18n.get('domain_tools.human_input.options', options=', '.join(options))}"

    default_section = ""
    if default_value:
        # default 同名碰撞：i18n.get 的 default 参数是缺失 key 时的回退值，
        # 若直接用 default=default_value 会吞掉模板变量 {default}。
        default_section = f"\n{i18n.get('domain_tools.human_input.default', context={'default': default_value})}"

    response_text = i18n.get(
        "domain_tools.human_input.request_template",
        id=request.id,
        type=input_type,
        prompt=prompt,
        context_section=context_section,
        options_section=options_section,
        default_section=default_section,
    )

    logger.info(f"Human input requested: {prompt[:50]}...")

    # Push HITL request via MessageHandler（push_hitl_notification 内部通过
    # ActivitySink 通知 monitoring，此处不再重复通知）。
    await push_hitl_notification(
        thread_id=thread_id,
        request=request,
        request_data={
            "id": request.id,
            "type": input_type,
            "prompt": prompt,
            "options": options,
            "context": context,
            "default_value": default_value,
        },
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        tool_name="question",
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
    )

    # Raise Interrupt Exception to pause execution
    raise_hitl_interrupt(request.id, response_text)


@evoloop_tool(
    "ask_confirm",
    args_schema=RequestApprovalArgs,
    is_hitl=True,
    summary_template="evoloop.tool_summary.ask_user",
    handle_tool_error=False,  # HITL must propagate interrupt exception
)
async def ask_confirm(
    action_description: str,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    details: str | None = None,
    consequences: str | None = None,
) -> str:
    """
    Request user approval before executing a potentially impactful action.

    Use this tool before:
    - Deleting or modifying important files
    - Running commands that could have side effects
    - Making irreversible changes
    - Executing operations with significant cost

    **注意**：若运营需要从多个候选中**挑选一部分**处理，应改用 ``ask_human``
    的 ``input_type="multi_choice"`` 让运营勾选，不要用本工具。

    The workflow will pause until the user responds.

    Returns "APPROVED" or "REJECTED" based on user decision.
    """
    # EXECUTION_MODE=docker：无人值守流水线不挂起，自动 APPROVED（沙箱隔离兜底）。
    if not hitl_enabled():
        logger.info(
            "[HITL] docker mode: ask_confirm auto-approved '%s' (sandbox isolation)",
            action_description[:50],
        )
        return HITLDecision.APPROVED.value

    ctx_fields = resolve_tool_context()
    thread_id = ctx_fields["thread_id"]
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    approval_context = build_approval_context(
        action_description=action_description,
        risk_level=risk_level,
        details=details,
        consequences=consequences,
    )

    logger.info(
        "Approval requested for: %s... (Risk: %s)",
        action_description[:50],
        risk_level,
    )

    from app.core.hitl.orchestrator import HITLOrchestrator

    return await HITLOrchestrator.raise_approval(
        thread_id=thread_id,
        prompt=action_description,
        context=approval_context,
        tool_name="ask_confirm",
        risk_level=risk_level,
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        original_tool_name="ask_confirm",
        response_text_factory=lambda req: i18n.get(
            "domain_tools.human_input.approval_template",
            id=req.id,
            approval_context=approval_context,
        ),
    )
