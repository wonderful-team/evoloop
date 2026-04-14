"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.evocloud import evocloud_manager
from app.core.exceptions import AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor
from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.conversation import HumanRequest

logger = logging.getLogger(__name__)


# ============ Data Models ============


class HumanInputRequest(BaseModel):
    """Stored request for human input (Pydantic model for internal use).
    
    Note: Timeout mechanism is intentionally NOT implemented.
    EvoLoop is an interactive assistant where users have full control.
    HITL requests will remain pending until user responds or explicitly cancels.
    """

    id: str
    thread_id: str
    request_type: Literal["text", "choice", "confirmation", "approval"]
    prompt: str
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["pending", "completed", "timeout", "cancelled"] = "pending"
    response: Any | None = None

    @classmethod
    def from_db(cls, db_model: HumanRequest):
        """Convert from SQLAlchemy model to Pydantic model."""
        return cls(
            id=db_model.id,
            thread_id=db_model.thread_id,
            request_type=db_model.type,  # Map type to request_type
            prompt=db_model.description,  # Map description to prompt
            options=db_model.options,
            context=db_model.context,
            default_value=db_model.default_value,
            created_at=db_model.created_at,
            status=db_model.status,
            response=db_model.result,
        )


# ============ Input Schemas ============


class RequestHumanInputArgs(BaseModel):
    prompt: str = Field(
        ..., description="The question or instruction to present to the user."
    )
    input_type: Literal["text", "choice", "confirmation"] = Field(
        "text",
        description="Type of input: 'text' for free-form, 'choice' for selection, 'confirmation' for yes/no.",
    )
    options: list[str] | None = Field(
        None,
        description="Required if input_type is 'choice'. List of options for user to select from.",
    )
    context: str | None = Field(
        None,
        description="Additional context to help the user understand what's needed.",
    )
    default_value: str | None = Field(
        None, description="Default value if user doesn't respond within timeout."
    )


class RequestApprovalArgs(BaseModel):
    action_description: str = Field(
        ..., description="Clear description of the action that requires approval."
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        "medium",
        description="Risk level of the action to help user make informed decision.",
    )
    details: str | None = Field(
        None, description="Detailed information about what will happen if approved."
    )
    consequences: str | None = Field(
        None, description="Potential consequences or impact of this action."
    )


# ============ Core Request Management ============


async def create_request(
    thread_id: str,
    request_type: str,
    prompt: str,
    options: list[str] | None = None,
    context: str | None = None,
    default_value: str | None = None,
) -> HumanInputRequest:
    """Create and store a human input request in the database."""
    request_id = str(uuid4())
    async with session_scope() as session:
        db_request = HumanRequest(
            id=request_id,
            thread_id=thread_id,
            type=request_type,
            description=prompt,
            options=options,
            context=context,
            default_value=default_value,
            status="pending",
        )
        session.add(db_request)
        # Flush to ensure it's saved but wait for commit in session_scope
        await session.flush()
        
        pydantic_req = HumanInputRequest.from_db(db_request)
        logger.info(f"Created human input request in DB: {request_id} ({request_type})")
        return pydantic_req


async def get_pending_request(request_id: str) -> HumanInputRequest | None:
    """Get a pending request by ID from the database."""
    async with session_scope() as session:
        db_request = await session.get(HumanRequest, request_id)
        if db_request:
            return HumanInputRequest.from_db(db_request)
    return None


async def get_pending_requests_for_thread(thread_id: str) -> list[HumanInputRequest]:
    """Get all pending requests for a specific thread from the database."""
    async with session_scope() as session:
        stmt = select(HumanRequest).where(
            HumanRequest.thread_id == thread_id, 
            HumanRequest.status == "pending"
        ).order_by(HumanRequest.created_at.asc())
        result = await session.execute(stmt)
        return [HumanInputRequest.from_db(req) for req in result.scalars().all()]


async def complete_request(request_id: str, response: Any) -> bool:
    """Complete a pending request with user's response in the database."""
    async with session_scope() as session:
        stmt = (
            update(HumanRequest)
            .where(HumanRequest.id == request_id)
            .values(status="completed", result=str(response))
        )
        result = await session.execute(stmt)
        success = result.rowcount > 0
        if success:
            logger.info(f"Completed human input request {request_id} in DB with response: {response}")
        return success


async def cancel_request(request_id: str) -> bool:
    """Cancel a pending request in the database."""
    async with session_scope() as session:
        stmt = (
            update(HumanRequest)
            .where(HumanRequest.id == request_id)
            .values(status="cancelled")
        )
        result = await session.execute(stmt)
        success = result.rowcount > 0
        if success:
            logger.info(f"Cancelled human input request {request_id} in DB")
        return success


# ============ Tools ============


@evoloop_tool(
    "ask_human",
    args_schema=RequestHumanInputArgs,
    is_pollable=True,
    summary_template="database_logger.tool_summary.ask_user",
    name_map={"zh": "询问用户", "en": "Ask Human"},
    handle_tool_error=False,  # HITL must propagate interrupt exception
)
async def ask_human(
    prompt: str,
    input_type: Literal["text", "choice", "confirmation"] = "text",
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
    from app.core.context.manager import ContextManager
    from app.core.monitoring.ui_actions import HumanRequestType

    try:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id or "unknown"
        project_id = ctx.project_id
        command_id = ctx.command_id
    except Exception:
        thread_id = "unknown"
        project_id = None
        command_id = None

    # Map internal type to standardized HumanRequestType
    type_map = {
        "text": HumanRequestType.TEXT_INPUT,
        "choice": HumanRequestType.TEXT_INPUT,  # Frontend handles choice via options in text_input/custom
        "confirmation": HumanRequestType.CONFIRM,
    }
    request_type = type_map.get(input_type, HumanRequestType.TEXT_INPUT)

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
    # The actual waiting/response handling is done by the frontend + API layer
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

    # Sync to EvoCloud (Mobile) - Backgrounded to ensure immediate interrupt
    try:
        asyncio.create_task(evocloud_manager.upload_log(
            thread_id=thread_id,
            log_type="hitl_request",
            content={
                "id": request.id,
                "type": input_type,
                "prompt": prompt,
                "options": options,
                "context": context,
                "default_value": default_value,
            },
            project_id=project_id,
            command_id=command_id,
        ))
    except Exception as e:
        logger.warning(f"Failed to initiate HITL request sync: {e}")

    # Raise Interrupt Exception to pause execution
    # This ensures the graph stops immediately
    raise AgentHumanInterruptException(request.id, response_text)


@evoloop_tool(
    "ask_confirm",
    args_schema=RequestApprovalArgs,
    is_pollable=True,
    summary_template="database_logger.tool_summary.ask_user",
    name_map={"zh": "确认操作", "en": "Ask Confirm"},
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
    from app.core.context.manager import ContextManager

    try:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id or "unknown"
        project_id = ctx.project_id
        command_id = ctx.command_id
    except Exception:
        thread_id = "unknown"
        project_id = None
        command_id = None

    # Build approval context
    risk_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴"
    }

    localized_risk = i18n.get(f"common.risk_levels.{risk_level}", default=risk_level.upper())

    approval_context = f"""
{risk_emoji.get(risk_level, '⚪')} {i18n.get("domain_tools.human_input.risk_level", level=localized_risk)}

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

    from app.core.monitoring.ui_actions import HumanRequestType

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

    # Sync to EvoCloud (Mobile) - Backgrounded
    try:
        asyncio.create_task(evocloud_manager.upload_log(
            thread_id=thread_id,
            log_type="hitl_request",
            content={
                "id": request.id,
                "type": "approval",
                "prompt": action_description,
                "context": approval_context,
                "default_value": "REJECTED",
                "risk_level": risk_level,
            },
            project_id=project_id,
            command_id=command_id,
        ))
    except Exception as e:
        logger.warning(f"Failed to initiate HITL approval sync: {e}")

    # Raise Interrupt Exception to pause execution
    raise AgentHumanInterruptException(request.id, response_text)


# ============ API Helpers ============


async def get_all_pending_requests() -> list[dict]:
    """Get all pending requests from database as dictionaries (for API responses)."""
    async with session_scope() as session:
        stmt = select(HumanRequest).where(HumanRequest.status == "pending")
        result = await session.execute(stmt)
        return [
            {
                "id": req.id,
                "thread_id": req.thread_id,
                "request_type": req.type,
                "prompt": req.description,
                "options": req.options,
                "context": req.context,
                "default_value": req.default_value,
                "created_at": req.created_at.isoformat(),
                "status": req.status,
            }
            for req in result.scalars().all()
        ]


async def cleanup_old_requests(max_age_hours: int = 24):
    """Remove old completed/cancelled requests from database."""
    from sqlalchemy import delete
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    
    async with session_scope() as session:
        stmt = delete(HumanRequest).where(
            HumanRequest.status.in_(["completed", "cancelled", "timeout"]),
            HumanRequest.created_at < cutoff
        )
        result = await session.execute(stmt)
        if result.rowcount > 0:
            logger.info(f"Cleaned up {result.rowcount} old human input requests from DB")
