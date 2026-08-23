"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.

This module is now a thin wrapper around app.core.hitl; the shared HITL primitives
live there so they can also be used by the authorization framework.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from app.core.hitl.batch_grants import create_pending_grant, update_grant_request_id
from app.core.hitl.core import create_request, push_hitl_notification, raise_hitl_interrupt
from app.core.hitl.prompts import build_approval_context, resolve_tool_context
from app.core.tools import evoloop_tool
from app.domain.tools.schemas import RequestApprovalArgs, RequestHumanInputArgs
from app.i18n.service import i18n
from app.utils.id import gen_uuid

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
    input_type: Literal["text", "choice", "multi_choice", "confirmation", "approval", "project_switch", "file_select"] = "text",
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

    **批量勾选处理范围（重要）**：当需要运营从多个同类待办中**挑选一部分**处理时
    （例如多笔退款/提现中只处理其中几笔），使用 ``input_type="multi_choice"``，
    在 ``options`` 中列出可勾选项（可给出"全部处理 / 仅处理某类 / 各单据编号"等）。
    运营可勾选多项，返回值是**逗号分隔的选中清单**；随后只执行清单内的项。
    不要为每一笔单独请求确认。

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
    operations: list[dict[str, Any]] | None = None,
    risk_note: str | None = None,
) -> str:
    """
    Request user approval before executing a potentially impactful action.

    Use this tool before:
    - Deleting or modifying important files
    - Running commands that could have side effects
    - Making irreversible changes
    - Executing operations with significant cost
    - Running multiple state-changing operations of the same kind in one turn
      (provide the full ``operations`` list for batch approval)

    When ``operations`` is provided, this becomes a batch approval: the user
    approves or rejects the entire list at once. Approved operations are covered
    by a short-lived grant and will not trigger per-call confirmation again.

    **注意**：若运营需要从清单中**只挑选一部分**处理（而非整批批准/驳回），应改
    用 ``ask_human`` 的 ``input_type="multi_choice"`` 让运营勾选，不要用本工具。

    The workflow will pause until the user responds.

    Returns "APPROVED" or "REJECTED" based on user decision.
    """
    ctx_fields = resolve_tool_context()
    thread_id = ctx_fields["thread_id"]
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    ops: list[dict[str, Any]] = []
    for op in operations or []:
        if isinstance(op, BaseModel):
            ops.append(op.model_dump())
        elif isinstance(op, dict):
            ops.append(op)
    if ops:
        detail_lines = []
        for i, op in enumerate(ops, 1):
            desc = op.get("description") or op.get("tool_name", "")
            macro_name = op.get("macro_name")
            macro_id = op.get("macro_id")
            if macro_name:
                desc = f"{desc} ({macro_name})"
            elif macro_id:
                desc = f"{desc} (macro_id={macro_id})"
            params = op.get("params") or {}
            params_str = ", ".join(f"{k}={v}" for k, v in params.items() if not k.startswith("_"))
            detail_lines.append(f"{i}. {desc}" + (f" ({params_str})" if params_str else ""))
        batch_details = "\n".join(detail_lines)
        combined_details = "\n\n".join(filter(None, [details, batch_details]))
        combined_consequences = "\n\n".join(filter(None, [consequences, risk_note]))
    else:
        combined_details = details
        combined_consequences = consequences

    approval_context = build_approval_context(
        action_description=action_description,
        risk_level=risk_level,
        details=combined_details,
        consequences=combined_consequences,
    )

    logger.info(
        "Approval requested for: %s... (Risk: %s, batch=%s)",
        action_description[:50],
        risk_level,
        bool(ops),
    )

    # Single-action approval: reuse the unified orchestrator path.
    if not ops:
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

    # Batch approval: create the grant first, then link it to the HITL request
    # so that post-approval resume can activate the grant.
    grant_id = gen_uuid()
    create_pending_grant(
        grant_id=grant_id,
        thread_id=thread_id,
        request_id="",
        operations=ops,
        ttl_seconds=300,
    )

    request = await create_request(
        thread_id=thread_id,
        request_type="approval",
        prompt=action_description,
        context=approval_context,
        default_value="REJECTED",
    )

    update_grant_request_id(grant_id, request.id)

    await push_hitl_notification(
        thread_id=thread_id,
        request=request,
        request_data={
            "id": request.id,
            "type": "approval",
            "prompt": action_description,
            "context": approval_context,
            "default_value": "REJECTED",
            "risk_level": risk_level,
            "batch_grant_id": grant_id,
            "operations": ops,
        },
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        tool_name="ask_confirm",
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
        original_tool_name="ask_confirm",
        original_tool_args={"grant_id": grant_id},
    )

    response_text = i18n.get(
        "domain_tools.human_input.approval_template",
        id=request.id,
        approval_context=approval_context,
    )
    raise_hitl_interrupt(request.id, response_text)
