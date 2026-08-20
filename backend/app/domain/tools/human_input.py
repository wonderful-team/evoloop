"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.

This module is now a thin wrapper around app.core.hitl; the shared HITL primitives
live there so they can also be used by the authorization framework.
"""

import logging
from typing import Literal

from app.core.hitl import (
    create_request,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.core.hitl.prompts import build_approval_context, resolve_tool_context
from app.core.tools import evoloop_tool
from app.domain.tools.schemas import RequestApprovalArgs, RequestHumanInputArgs
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


# ============ Tools ============


@evoloop_tool(
    "ask_human",
    args_schema=RequestHumanInputArgs,
    is_hitl=True,
    summary_template="evoloop.tool_summary.ask_user",
    handle_tool_error=False,  # HITL must propagate interrupt exception
)
async def ask_human(
    prompt: str,
    input_type: Literal["text", "choice", "confirmation", "approval", "project_switch", "file_select"] = "text",
    options: list[str] | None = None,
    context: str | None = None,
    default_value: str | None = None,
) -> str:
    """
    Pause execution and request input from the user.

    Use this tool when you:
    - Need information that only the user can provide
    - Require clarification on requirements
    - Want user to make a decision between options
    - Need confirmation before proceeding

    The workflow will pause until the user responds.

    Returns the user's response as a string.
    """
    ctx_fields = resolve_tool_context()
    thread_id = ctx_fields["thread_id"]
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    # input_type 是 Literal 受限字符串，其值即标准 request_type
    #（与 HumanRequestType 枚举值一致），直接透传给 create_request 校验。

    # Validate choice options
    if input_type == "choice" and not options:
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

    # Push HITL request via MessageHandler (push_hitl_notification 内部会
    # 同步调用 activity_monitor.set_human_request，此处不再重复通知)。
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
        tool_name="ask_human",
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
    risk_level: Literal["low", "medium", "high", "critical"] = "medium",
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

    The workflow will pause until the user approves or rejects.

    Returns "APPROVED" or "REJECTED" based on user decision.
    """
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
        "Approval requested for: %s... (Risk: %s, batch=%s)",
        action_description[:50],
        risk_level,
        bool(ops),
    )

    # 统一发起 approval（create + push + raise），用 i18n 模板生成响应文本
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
        response_text_factory=lambda req: i18n.get(
            "domain_tools.human_input.approval_template",
            id=req.id,
            approval_context=approval_context,
        ),
    )
