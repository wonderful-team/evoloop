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
from app.core.monitoring.schemas import HumanRequestType
from app.infrastructure.database import session_scope
from app.models import Message
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
    # Fail-fast: validate request_type against the canonical enum (fail-fast
    # per AGENTS.md; an invalid type would otherwise be silently persisted).
    valid_types = {t.value for t in HumanRequestType}
    if request_type not in valid_types:
        raise ValueError(
            f"Invalid request_type {request_type!r}; expected one of {sorted(valid_types)}"
        )

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


async def finalize_request(
    thread_id: str,
    request_id: str | None,
    tool_call_id: str | None,
    status: Literal["completed", "cancelled"],
    response: Any | None = None,
    sibling_key: dict | None = None,
) -> bool:
    """Atomically finalize a HITL request across BOTH the human_requests table
    and the messages (hitl_request) table in a single transaction.

    This replaces the previous two-step close-then-update sequence, which ran
    in separate transactions and could leave the two state tracks (A:
    human_requests, B: messages) out of sync on partial failure.

    ``tool_call_id`` may be ``None`` when the request was created outside a
    tool execution context; in that case only the human_requests track is
    updated (there is no corresponding message to close).

    ``sibling_key``（``{"name": ..., "args": ...}``，由调用方从 pending_tool 传入）
    用于关闭同线程下同工具+同参数的兄弟 pending 请求——Agent 重试可能为同一
    工具创建多条 approval 请求，运营批准一条后其余残留 pending（见 handoff
    mcp-confirm-gap §3.4）。未传则跳过（无额外查询开销）。
    """
    async with session_scope() as session:
        updated_request = False
        if request_id:
            req_stmt = (
                update(HumanRequest)
                .where(
                    HumanRequest.id == request_id,
                    HumanRequest.status == "pending",
                )
                .values(status=status, result=str(response) if response is not None else None)
            )
            updated_request = (await session.execute(req_stmt)).rowcount > 0

        updated_message = False
        if tool_call_id:
            msg_stmt = (
                update(Message)
                .where(Message.thread_id == thread_id)
                .where(Message.tool_call_id == tool_call_id)
                .values(status=status)
            )
            updated_message = (await session.execute(msg_stmt)).rowcount > 0

        if tool_call_id and status == "completed" and sibling_key:
            await _close_sibling_requests(session, thread_id, tool_call_id, status, sibling_key)

        logger.info(
            "[HITL] finalized request=%s tool=%s status=%s (human_requests=%s, messages=%s)",
            request_id, tool_call_id, status, updated_request, updated_message,
        )
        return updated_request or updated_message


async def _close_sibling_requests(
    session, thread_id: str, tool_call_id: str, status: str, sibling_key: dict
) -> None:
    """关闭同线程下与 ``sibling_key`` 同工具+同参数的兄弟 pending 请求（双轨）。

    仅在调用方传入 ``sibling_key`` 时执行（含 ``original_tool`` 元数据的门控
    请求）；普通 HITL 工具（ask_confirm/ask_human 等）不传，不会被误匹配。
    """
    try:
        name = sibling_key.get("name")
        args = sibling_key.get("args") or {}
        if not name:
            return

        # 查同线程其他 waiting_human 的 hitl_request 消息（同 original_tool）
        siblings = await session.execute(
            select(Message)
            .where(
                Message.thread_id == thread_id,
                Message.role == "system",
                Message.category == "hitl_request",
                Message.status == "waiting_human",
                Message.tool_call_id != tool_call_id,
            )
        )
        closed = 0
        for sibling in siblings.scalars().all():
            smeta = sibling.meta_data or {}
            s_tool = smeta.get("original_tool") or {}
            if s_tool.get("name") != name:
                continue
            if (s_tool.get("args") or {}) != args:
                continue
            # 关闭 messages 轨
            await session.execute(
                update(Message)
                .where(Message.id == sibling.id)
                .values(status=status)
            )
            # 关闭 human_requests 轨（meta_data.hitl_request_id）
            s_req_id = smeta.get("hitl_request_id")
            if s_req_id:
                await session.execute(
                    update(HumanRequest)
                    .where(
                        HumanRequest.id == s_req_id,
                        HumanRequest.status == "pending",
                    )
                    .values(status=status)
                )
            closed += 1

        if closed:
            logger.info(
                "[HITL] Closed %d sibling request(s) matching %s %s (thread=%s)",
                closed, name, args, thread_id,
            )
    except Exception as e:
        # 批量关闭是优化非关键路径，失败不应阻断主流程 finalize。
        logger.warning(f"[HITL] Failed to close sibling requests: {e}", exc_info=True)


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
    skip_grant: bool = False,
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
        if skip_grant:
            metadata["authorization"] = metadata.get("authorization") or {}
            metadata["authorization"]["skip_grant"] = True
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
    except Exception as e:
        logger.warning(f"Failed to push HITL request via MessageHandler: {e}", exc_info=True)


def raise_hitl_interrupt(request_id: str, response_text: str) -> None:
    """Raise the interrupt exception that pauses graph execution."""
    raise AgentHumanInterruptException(request_id, response_text)
