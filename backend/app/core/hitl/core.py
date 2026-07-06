"""
HITL core: shared primitives for Human-in-the-Loop interactions.

This module intentionally stays independent from the tool layer so that it can be
used both by explicit HITL tools (ask_human, ask_confirm) and by the authorization
framework running inside hooks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.exceptions import AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database import session_scope
from app.models.conversation import HumanRequest
from app.utils.id import gen_uuid

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
    request_type: Literal[
        "text",
        "choice",
        "confirmation",
        "approval",
        "project_switch",
        "file_select",
    ]
    prompt: str
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["pending", "completed", "timeout", "cancelled"] = "pending"
    response: Any | None = None

    @classmethod
    def from_db(cls, db_model: HumanRequest) -> "HumanInputRequest":
        """Convert from SQLAlchemy model to Pydantic model."""
        return cls(
            id=db_model.id,
            thread_id=db_model.thread_id,
            request_type=db_model.type,
            prompt=db_model.description,
            options=db_model.options,
            context=db_model.context,
            default_value=db_model.default_value,
            created_at=db_model.created_at,
            status=db_model.status,
            response=db_model.result,
        )


# ============ DB Request Management ============


async def create_request(
    thread_id: str,
    request_type: str,
    prompt: str,
    options: list[str] | None = None,
    context: str | None = None,
    default_value: str | None = None,
) -> HumanInputRequest:
    """Create and store a human input request in the database."""
    request_id = gen_uuid()
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
        stmt = (
            select(HumanRequest)
            .where(
                HumanRequest.thread_id == thread_id, HumanRequest.status == "pending"
            )
            .order_by(HumanRequest.created_at.asc())
        )
        result = await session.execute(stmt)
        return [HumanInputRequest.from_db(req) for req in result.scalars().all()]


async def complete_request(request_id: str, response: Any) -> bool:
    """Complete a pending request with user's response in the database."""
    async with session_scope() as session:
        stmt = (
            update(HumanRequest)
            .where(
                HumanRequest.id == request_id,
                HumanRequest.status == "pending",
            )
            .values(status="completed", result=str(response))
        )
        result = await session.execute(stmt)
        success = result.rowcount > 0
        if success:
            logger.info(
                f"Completed human input request {request_id} in DB with response: {response}"
            )
        return success


async def cancel_request(request_id: str) -> bool:
    """Cancel a pending request in the database."""
    async with session_scope() as session:
        stmt = (
            update(HumanRequest)
            .where(
                HumanRequest.id == request_id,
                HumanRequest.status == "pending",
            )
            .values(status="cancelled")
        )
        result = await session.execute(stmt)
        success = result.rowcount > 0
        if success:
            logger.info(f"Cancelled human input request {request_id} in DB")
        return success


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


async def cleanup_old_requests(max_age_hours: int = 24) -> int:
    """Remove old completed/cancelled requests from database."""
    from datetime import timedelta

    from sqlalchemy import delete

    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    async with session_scope() as session:
        stmt = delete(HumanRequest).where(
            HumanRequest.status.in_(["completed", "cancelled", "timeout"]),
            HumanRequest.created_at < cutoff,
        )
        result = await session.execute(stmt)
        count = result.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} old human input requests from DB")
        return count


# ============ Notification & Interrupt ============


async def push_hitl_notification(
    thread_id: str,
    request: HumanInputRequest,
    request_data: dict,
    project_id: int | None = None,
    run_id: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    parent_id: str | None = None,
    original_tool_name: str | None = None,
    original_tool_args: dict | None = None,
    resource_path: str | None = None,
    action: str | None = None,
) -> None:
    """
    Push a HITL request to the activity monitor and the message handler.

    This is the shared notification path used by both explicit HITL tools and the
    authorization framework.
    """
    # 1. Notify Activity Monitor with structured data
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data=request_data,
    )

    # 2. Push via MessageHandler for real-time UI delivery
    try:
        from app.core.engine.message import MessageHandler

        handler = MessageHandler(
            thread_id=thread_id,
            project_id=project_id,
            run_id=run_id,
        )
        metadata = {}
        if original_tool_name or original_tool_args:
            metadata["original_tool"] = {
                "name": original_tool_name,
                "args": original_tool_args or {},
            }
        if resource_path or action:
            metadata["authorization"] = {
                "resource_path": resource_path,
                "action": action,
                "project_id": project_id,
            }
        asyncio.create_task(
            handler.handle_hitl_request(
                request_type=request.request_type,
                prompt=request.prompt,
                request_id=request.id,
                options=request.options,
                context=request.context,
                default_value=request.default_value,
                tool_call_id=tool_call_id,
                tool_name=tool_name or request.request_type,
                parent_id=parent_id,
                metadata=metadata if metadata else None,
            )
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to push HITL request via MessageHandler: {e}")


def raise_hitl_interrupt(request_id: str, response_text: str) -> None:
    """Raise the interrupt exception that pauses graph execution."""
    raise AgentHumanInterruptException(request_id, response_text)


async def create_and_raise_hitl_request(
    thread_id: str,
    request_type: str,
    prompt: str,
    response_text: str,
    request_data: dict,
    options: list[str] | None = None,
    context: str | None = None,
    default_value: str | None = None,
    project_id: int | None = None,
    run_id: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    parent_id: str | None = None,
) -> HumanInputRequest:
    """
    One-shot helper: create the DB record, push notifications, and raise interrupt.

    Returns the created request (mostly for testing); normal control flow never
    reaches the return because raise_hitl_interrupt raises.
    """
    request = await create_request(
        thread_id=thread_id,
        request_type=request_type,
        prompt=prompt,
        options=options,
        context=context,
        default_value=default_value,
    )

    await push_hitl_notification(
        thread_id=thread_id,
        request=request,
        request_data={"id": request.id, **request_data},
        project_id=project_id,
        run_id=run_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        parent_id=parent_id,
    )

    raise_hitl_interrupt(request.id, response_text)
    # Unreachable, but keeps type checkers happy
    return request
