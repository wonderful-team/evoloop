"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.

This module is now a thin wrapper around app.core.hitl; the shared HITL primitives
live there so they can also be used by the authorization framework.
"""
import logging
from typing import Literal

from app.core.context.manager import ContextManager
from app.core.hitl import (
    create_request,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.ui_actions import HumanRequestType
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
    try:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id or "unknown"
        project_id = ctx.project_id
        command_id = ctx.command_id
        current_tool_call_id = ctx.current_tool_call_id
        last_ai_message_id = ctx.last_ai_message_id
    except Exception:
        thread_id = "unknown"
        project_id = None
        command_id = None
        current_tool_call_id = None
        last_ai_message_id = None

    # Map internal type to standardized HumanRequestType
    type_map = {
        "text": HumanRequestType.TEXT,
        "choice": HumanRequestType.CHOICE,
        "confirmation": HumanRequestType.CONFIRMATION,
        "approval": HumanRequestType.APPROVAL,
        "project_switch": HumanRequestType.PROJECT_SWITCH,
        "file_select": HumanRequestType.FILE_SELECT,
    }
    request_type = type_map.get(input_type, HumanRequestType.TEXT)

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
        context_section = f"\n{i18n.get('domain_tools.human_input.context', context=context)}"

    options_section = ""
    if options:
        options_section = f"\n{i18n.get('domain_tools.human_input.options', options=', '.join(options))}"

    default_section = ""
    if default_value:
        default_section = f"\n{i18n.get('domain_tools.human_input.default', default=default_value)}"

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

    # Notify Activity Monitor with Structured Data
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data={
            "id": request.id,
            "type": request_type,
            "prompt": prompt,
            "options": options,
            "context": context,
            "default_value": default_value,
        },
    )

    # Push HITL request via MessageHandler
    await push_hitl_notification(
        thread_id=thread_id,
        request=request,
        request_data={
            "id": request.id,
            "type": request_type,
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
    try:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id or "unknown"
        project_id = ctx.project_id
        command_id = ctx.command_id
        current_tool_call_id = ctx.current_tool_call_id
        last_ai_message_id = ctx.last_ai_message_id
    except Exception:
        thread_id = "unknown"
        project_id = None
        command_id = None
        current_tool_call_id = None
        last_ai_message_id = None

    # Build approval context
    risk_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }

    localized_risk = i18n.get(f"common.risk_levels.{risk_level}", default=risk_level.upper())

    approval_context = f"""
{risk_emoji.get(risk_level, "⚪")} {i18n.get("domain_tools.human_input.risk_level", level=localized_risk)}

{i18n.get("domain_tools.human_input.action", action=action_description)}
"""

    if details:
        approval_context += f"\n{i18n.get('domain_tools.human_input.details', details=details)}\n"

    if consequences:
        approval_context += f"\n{i18n.get('domain_tools.human_input.consequences', conseq=consequences)}\n"

    # Create the request
    request = await create_request(
        thread_id=thread_id,
        request_type="approval",
        prompt=action_description,
        context=approval_context,
        default_value="REJECTED",  # Default to safe option
    )

    response_text = i18n.get(
        "domain_tools.human_input.approval_template",
        id=request.id,
        approval_context=approval_context,
    )

    logger.info(f"Approval requested for: {action_description[:50]}... (Risk: {risk_level})")

    # Notify Activity Monitor with Structured Data
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data={
            "id": request.id,
            "type": HumanRequestType.APPROVAL,
            "prompt": action_description,
            "context": approval_context,
            "default_value": "REJECTED",
            "risk_level": risk_level,
        },
    )

    # Push HITL approval via MessageHandler
    await push_hitl_notification(
        thread_id=thread_id,
        request=request,
        request_data={
            "id": request.id,
            "type": HumanRequestType.APPROVAL,
            "prompt": action_description,
            "context": approval_context,
            "default_value": "REJECTED",
            "risk_level": risk_level,
        },
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        tool_name="ask_confirm",
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
    )

    # Raise Interrupt Exception to pause execution
    raise_hitl_interrupt(request.id, response_text)
