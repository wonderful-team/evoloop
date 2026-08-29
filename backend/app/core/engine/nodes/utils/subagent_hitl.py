"""Subagent HITL passthrough — transparent forwarding of subagent HITL to the parent.

Design: docs/subagent-design.md §5.5. A subagent can trigger ask_human /
request_authorization; the request is forwarded via SubagentHITLRequestEvent to
the parent session, the parent asks the user in the main session UI, and the
answer is routed back via ``respond_subagent_hitl`` (which reuses the normal
HITL resume primitive + rebuilds the subagent execution body).
"""

import asyncio
import logging

from app.core.engine.session.manager import session_manager
from app.core.events.schemas.subagent import SubagentHITLRequestEvent

logger = logging.getLogger(__name__)


async def mark_subagent_awaiting_human_and_publish(thread_id: str) -> None:
    """Mark the SubagentRun as awaiting_human and publish the passthrough event.

    Called from the subagent execution body when it exits on AgentHumanInterrupt.
    """
    from sqlalchemy import select

    from app.core.context.manager import ContextManager
    from app.infrastructure.database import session_scope
    from app.models.subagent import SubagentRun

    ctx = ContextManager.current()
    if not ctx or ctx.metadata.get("task_type") != "subagent":
        return

    parent_tid = ctx.metadata.get("parent_thread_id") or ""
    subagent_id = ctx.metadata.get("subagent_id") or ""
    model = ctx.active_model

    from app.core.hitl.orchestrator import HITLOrchestrator

    pending = await HITLOrchestrator.get_pending_request(thread_id, model)
    if not pending:
        logger.warning(
            f"[SubagentHITL] No pending HITL on {thread_id}; nothing to forward"
        )
        return

    args = pending.get("args") or {}
    request_type = pending.get("request_type") or pending.get("name") or "ask_human"
    tool_call_id = pending.get("id") or pending.get("request_id") or ""

    async with session_scope() as session:
        stmt = select(SubagentRun).where(SubagentRun.thread_id == thread_id)
        run = (await session.execute(stmt)).scalar_one_or_none()
        if run and run.status == "running":
            run.status = "awaiting_human"

    # Publish to the parent thread's queue (system_bus subscriber routes it).
    from app.core.events import system_bus

    await system_bus.publish(
        SubagentHITLRequestEvent(
            thread_id=parent_tid,
            subagent_thread_id=thread_id,
            subagent_id=subagent_id,
            request_type=str(request_type),
            prompt=str(
                args.get("prompt") or args.get("context") or pending.get("name") or ""
            ),
            options=list(args.get("options") or []),
            context=str(args.get("context") or ""),
            tool_call_id=tool_call_id,
            risk_level=args.get("risk_level"),
            resource_path=args.get("resource_path"),
        )
    )
    logger.info(
        f"[SubagentHITL] Forwarded HITL ({request_type}) from {thread_id} to parent {parent_tid}"
    )


async def respond_subagent_hitl(sub_tid: str, answer: str) -> None:
    """Parent Supervisor routes the user's answer back to a hanging subagent."""
    from app.core.context.manager import ContextManager
    from app.core.engine.background_agent import run_subagent_background
    from app.core.engine.background_agent.models import BackgroundAgentInputs

    ctx = await ContextManager.load(sub_tid)
    pending = None
    if ctx:
        from app.core.hitl.orchestrator import HITLOrchestrator

        pending = await HITLOrchestrator.get_pending_request(
            sub_tid, ctx.active_model if ctx else None
        )
    if not pending:
        logger.warning(
            f"[SubagentHITL] No pending HITL request on {sub_tid}; response dropped"
        )
        return

    from app.core.hitl.orchestrator import HITLOrchestrator

    await HITLOrchestrator.handle_resume(sub_tid, pending, answer)

    # Rebuild the lightweight execution body (same resume primitive as normal HITL).
    inputs = BackgroundAgentInputs(
        hitl_resume_response=answer,
        model=ctx.active_model if ctx else None,
        metadata={"task_type": "subagent"},
        ticket=None,  # state rebuilt from DB; ticket restored by rebuild logic
    )
    asyncio.create_task(run_subagent_background(sub_tid, inputs))
    logger.info(f"[SubagentHITL] Resumed subagent {sub_tid} with user answer")


async def clear_subagent_hitl_route(parent_tid: str, sub_tid: str) -> None:
    """Remove a sub_tid from the parent's active_subagent_hitl routing table."""
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    if not ctx:
        return
    # The routing table lives on the parent AgentState; best-effort removal via
    # the session manager's state is handled by the supervisor's cancel path.
    try:
        session = session_manager.get(parent_tid)
        if session is not None and session.state is not None:
            active = dict(session.state.active_subagent_hitl or {})
            active.pop(sub_tid, None)
            session.state.active_subagent_hitl = active
    except Exception as e:
        logger.debug(f"[SubagentHITL] clear route skipped: {e}")
