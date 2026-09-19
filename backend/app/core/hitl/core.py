"""
HITL core: shared primitives for Human-in-the-Loop interactions.

This module intentionally stays independent from the tool layer so that it can be
used both by explicit HITL tools (ask_human, ask_confirm) and by the authorization
framework running inside hooks.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.engine.message.constants import MessageStatus
from app.core.exceptions import AgentHumanInterruptException
from app.core.execution.execution_mode import is_docker_mode
from app.core.hitl.activity_sink import get_activity_sink
from app.core.hitl.constants import MESSAGE_CATEGORY_HITL_REQUEST
from app.core.hitl.engine_runtime import get_runtime
from app.core.hitl.types import HITLDecision, HITLRequestStatus, HumanRequestType
from app.infrastructure.database import session_scope
from app.models import Message
from app.models.conversation import HumanRequest
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


# ============ Execution-mode guard ============


def hitl_enabled() -> bool:
    """HITL 是否生效。

    EXECUTION_MODE=docker 时豁免全部 HITL 拦截：无人值守流水线不应因审批/提问
    而挂起，命令与文件访问由沙箱容器隔离兜底（项目 .evoloop 元数据仍硬拦截，
    不在本引导范围内）。
    docker 判定单一出处：execution.execution_mode.is_docker_mode（进程事实模式）。
    """
    return not is_docker_mode()


def auto_hitl_response(
    request_type: str,
    default_value: str | None = None,
    options: list[str] | None = None,
) -> str:
    """docker 模式下无人值守的自动应答。

    approval/confirmation → APPROVED；其次用 default_value；再其次用首个选项；
    兜底返回空串。
    """
    if request_type in (
        HumanRequestType.APPROVAL.value,
        HumanRequestType.CONFIRMATION.value,
    ):
        return HITLDecision.APPROVED.value
    if default_value:
        return default_value
    if options:
        return options[0]
    return ""


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
        "multi_choice",
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
    status: Literal["pending", "completed", "timeout", "cancelled"] = (
        HITLRequestStatus.PENDING.value
    )
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
            status=HITLRequestStatus.PENDING.value,
        )
        session.add(db_request)
        await session.flush()

        pydantic_req = HumanInputRequest.from_db(db_request)
        logger.info(f"Created human input request in DB: {request_id} ({request_type})")

    # 值守工作台实时感知：Agent 发起审批 → 任务频道广播 hitl_created
    # （桌面/手机工作台即时弹出"等待审批"，不再依赖 10s 盲轮）。
    # session_scope 正常退出即已提交，广播失败不影响创建本身。
    try:
        from app.core.engine.message.broker import get_message_broker

        await get_message_broker().publish(
            "tasks:all:events",
            {
                "type": "task_queue_updated",
                "event": "hitl_created",
                "thread_id": thread_id,
                "request_id": request_id,
                "request_type": request_type,
            },
        )
    except Exception:
        pass

    return pydantic_req


async def get_pending_requests_for_thread(thread_id: str) -> list[HumanInputRequest]:
    """Get all pending requests for a specific thread from the database."""
    async with session_scope() as session:
        stmt = (
            select(HumanRequest)
            .where(
                HumanRequest.thread_id == thread_id,
                HumanRequest.status == HITLRequestStatus.PENDING.value,
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
                HumanRequest.status == HITLRequestStatus.PENDING.value,
            )
            .values(status=HITLRequestStatus.CANCELLED.value)
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
    工具创建多条 approval 请求，运营批准一条后其余残留 pending。未传则跳过
    （无额外查询开销）。
    """
    async with session_scope() as session:
        updated_request = False
        if request_id:
            req_stmt = (
                update(HumanRequest)
                .where(
                    HumanRequest.id == request_id,
                    HumanRequest.status == HITLRequestStatus.PENDING.value,
                )
                .values(
                    status=status,
                    result=str(response) if response is not None else None,
                )
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

        if tool_call_id and status == HITLRequestStatus.COMPLETED.value and sibling_key:
            await _close_sibling_requests(
                session, thread_id, tool_call_id, status, sibling_key
            )

        logger.info(
            "[HITL] finalized request=%s tool=%s status=%s (human_requests=%s, messages=%s)",
            request_id,
            tool_call_id,
            status,
            updated_request,
            updated_message,
        )
        # 值守工作台实时感知：审批定局 → 任务频道广播（任意端——桌面/手机——
        # 做出响应，工作台的"等待审批"计数即时回落，无需轮询收敛）
        if updated_request or updated_message:
            try:
                from app.core.engine.message.broker import get_message_broker

                await get_message_broker().publish(
                    "tasks:all:events",
                    {
                        "type": "task_queue_updated",
                        "event": "hitl_resolved",
                        "thread_id": thread_id,
                        "request_id": request_id,
                        "status": status,
                    },
                )
            except Exception:
                pass  # 通知失败不影响定局本身

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
            select(Message).where(
                Message.thread_id == thread_id,
                Message.role == "system",
                Message.category == MESSAGE_CATEGORY_HITL_REQUEST,
                Message.status == MessageStatus.WAITING_HUMAN,
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
                update(Message).where(Message.id == sibling.id).values(status=status)
            )
            # 关闭 human_requests 轨（meta_data.hitl_request_id）
            s_req_id = smeta.get("hitl_request_id")
            if s_req_id:
                await session.execute(
                    update(HumanRequest)
                    .where(
                        HumanRequest.id == s_req_id,
                        HumanRequest.status == HITLRequestStatus.PENDING.value,
                    )
                    .values(status=status)
                )
            closed += 1

        if closed:
            logger.info(
                "[HITL] Closed %d sibling request(s) matching %s %s (thread=%s)",
                closed,
                name,
                args,
                thread_id,
            )
    except Exception as e:
        # 批量关闭是优化非关键路径，失败不应阻断主流程 finalize。
        logger.warning(f"[HITL] Failed to close sibling requests: {e}", exc_info=True)


# ============ Request Dedup Helpers ============


async def _find_pending_by_key(
    thread_id: str, tool_name: str, tool_args: dict
) -> dict | None:
    """查找同线程下同工具+同参数的已有 pending approval 请求。

    避免 Agent 重试同一写操作时产生重复 approval 请求（源头去重）：
    命中则复用已有请求（``hitl_request_id`` + ``context``），不创建新请求。

    Returns:
        ``{"request_id": ..., "context": ...}`` 或 None。
    """
    try:
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(
                    Message.thread_id == thread_id,
                    Message.role == "system",
                    Message.category == MESSAGE_CATEGORY_HITL_REQUEST,
                    Message.status == MessageStatus.WAITING_HUMAN,
                )
                .order_by(Message.sequence_number.desc())
            )
            res = await session.execute(stmt)
            for msg in res.scalars().all():
                meta = msg.meta_data or {}
                original = meta.get("original_tool") or {}
                if original.get("name") != tool_name:
                    continue
                if (original.get("args") or {}) != tool_args:
                    continue
                req_id = meta.get("hitl_request_id")
                if req_id:
                    return {
                        "request_id": req_id,
                        "context": meta.get("hitl_context") or "",
                    }
    except Exception as e:
        logger.warning(f"[HITL] Failed to find pending by key: {e}")
    return None


async def find_recently_approved_by_key(
    thread_id: str, tool_name: str, tool_args: dict, window_seconds: int = 300
) -> str | None:
    """查找同线程下同工具+同参数**最近已批准**的请求。

    防止 Agent/LLM 在批准后因未收到结束信号而反复发起同一写操作（循环
    调用 run_macro），每次循环都产生新的 approval 请求。若同 key 在窗口内
    已批准（completed），视为"已确认过"，返回该请求 ID 供调用方复用批准语义。

    Returns:
        最近已批准请求的 request_id，或 None。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(
                    Message.thread_id == thread_id,
                    Message.role == "system",
                    Message.category == MESSAGE_CATEGORY_HITL_REQUEST,
                    Message.status.in_([HITLRequestStatus.COMPLETED.value]),
                    Message.updated_at >= cutoff,
                )
                .order_by(Message.updated_at.desc())
            )
            res = await session.execute(stmt)
            for msg in res.scalars().all():
                meta = msg.meta_data or {}
                original = meta.get("original_tool") or {}
                if original.get("name") != tool_name:
                    continue
                if (original.get("args") or {}) != tool_args:
                    continue
                req_id = meta.get("hitl_request_id")
                if req_id:
                    logger.info(
                        "[HITL] Reusing recently approved request=%s for %s (thread=%s)",
                        req_id,
                        tool_name,
                        thread_id,
                    )
                    return req_id
    except Exception as e:
        logger.warning(f"[HITL] Failed to find recently approved by key: {e}")
    return None


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
    resume_override: dict | None = None,
) -> None:
    """
    Push a HITL request to the activity monitor and the message handler.

    This is the shared notification path used by both explicit HITL tools and the
    authorization framework.

    ``resume_override``：审批后重执行时的门控豁免声明，由发起端（如宏确认）
    在发起时声明，resume 端按声明注入 ``{"args": {...}}``，避免按工具名特判。
    """
    # 1. Notify Activity Monitor with structured data
    await get_activity_sink().set_human_request(
        thread_id=thread_id,
        request_data=request_data,
    )

    # 2. Assemble authorization/resume metadata (hitl domain, stays here)
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
    if resume_override:
        metadata["resume"] = resume_override

    # 3. Push via EngineRuntime for real-time UI delivery. subagent 透传判断
    #    （"问人始终发生在主会话"）与 MessageHandler 后台任务均由 engine
    #    runtime 完成——hitl 只依赖协议，不再反向引用 engine。
    try:
        get_runtime().push_hitl_request(
            thread_id=thread_id,
            project_id=project_id,
            run_id=run_id,
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
    except Exception as e:
        logger.warning(f"Failed to push HITL request via EngineRuntime: {e}")


def raise_hitl_interrupt(request_id: str, response_text: str) -> None:
    """Raise the interrupt exception that pauses agent execution.

    EXECUTION_MODE=docker 时豁免：调用方已提前进入自动放行语义，此处兜底
    保证任何残留路径都不会再抛中断（避免无人值守流水线被挂起）。
    """
    if not hitl_enabled():
        logger.warning(
            "[HITL] docker mode: suppressing interrupt for request %s (sandbox isolation)",
            request_id,
        )
        return
    raise AgentHumanInterruptException(request_id, response_text)
