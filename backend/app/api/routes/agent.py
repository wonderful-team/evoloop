import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserOptional,
    verify_guest_access,
)
from app.api.responses import BaseAPIResponse
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext

# --- Background Worker ---
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.graph_runner import resume_graph_background
from app.core.evocloud import evocloud_manager
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.domain.integration.adapters import EventAdapter
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import Message
from app.models.learning import LearnedSkill
from app.models.schemas.base import ScopedRequest
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_pending_tool_call(graph, config: dict) -> dict | None:
    """Check if the graph's last message has a pending HITL tool call.

    Returns the tool_call dict if pending (request_approval / request_human_input),
    else None.  All exceptions are swallowed to avoid breaking the resume path.
    """
    try:
        current_state = await graph.aget_state(config)
        if not current_state.values or "messages" not in current_state.values:
            return None
        history = current_state.values["messages"]
        if not history:
            return None
        last_msg = history[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            last_tool_call = last_msg.tool_calls[-1]
            if last_tool_call["name"] in ("request_approval", "request_human_input"):
                return last_tool_call
    except Exception:
        pass
    return None


class ChatRequest(ScopedRequest):
    thread_id: str | None = None
    message: str
    project_id: int | None = 1
    model: str | None = None  # User selected model (optional)
    command_id: int | None = None
    checkpoint_id: str | None = None
    message_id: int | None = None  # Targeted retry/edit support
    attachments: list[dict[str, Any]] | None = None  # [{"url": "...", "type": "image"}]
    skill_id: int | None = None  # Attach a learned skill to the message
    revert_files: bool = True  # For retry/undo support


class WebhookPayload(DynamicBaseModel):
    """External webhook payload. Extra fields are allowed per source/event_type."""


class WebhookRequest(ScopedRequest):
    source: str
    event_type: str
    payload: WebhookPayload
    thread_id: str | None = None


class ResumeRequest(ScopedRequest):
    thread_id: str
    user_input: str | None = None  # Optional user response for HITL
    command_id: int | None = None  # Explicit command_id for resumption trace
    model: str | None = None  # User selected model (optional)


class CancelHITLRequest(ScopedRequest):
    thread_id: str
    reason: str | None = None  # Optional reason for cancellation
    model: str | None = None  # User selected model (optional)


class StopChatResponse(BaseAPIResponse):
    """Response for stopping a chat."""
    status: str
    thread_id: str


class ResumeChatResponse(BaseAPIResponse):
    """Response for resuming a chat."""
    status: str
    thread_id: str


class CancelHITLResponse(BaseAPIResponse):
    """Response for cancelling a HITL request."""
    status: str
    thread_id: str
    request_id: str | None


class WebhookResponse(BaseAPIResponse):
    """Response for webhook endpoint."""
    status: str
    thread_id: str


# =============================================================================
# Unified Dispatch Helpers
# =============================================================================


@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks, _current_user: CurrentUserOptional):
    """
    Unified entry point for User Chat (Local Background Task).
    """
    if not req.thread_id:
        req.thread_id = str(uuid.uuid4())

    ctx = EvoContext(
        request_id=f"req-{req.thread_id}-{int(time.time())}",
        thread_id=req.thread_id,
        project_id=req.project_id,
        command_id=req.command_id,
        active_model=req.model
    )
    ContextManager.set(ctx)

    # Process skill_id if provided
    attachments = req.attachments or []
    if req.skill_id:
        # Fetch skill info and add as attachment
        try:
            async with session_scope() as session:
                skill = await session.get(LearnedSkill, req.skill_id)
                if skill:
                    attachments.append({
                        "id": str(skill.id),
                        "type": "skill",
                        "name": skill.name,
                        "metadata": {
                            "skill_id": skill.id,
                            "skill_name": skill.name,
                            "description": skill.description
                        }
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch skill {req.skill_id}: {e}")

    logger.debug(f"[ChatEndpoint] Run initialized for thread {req.thread_id}")

    # Use Unified Dispatcher
    result = await dispatch_agent_run(
        thread_id=req.thread_id,
        message_content=req.message,
        project_id=req.project_id,
        attachments=attachments,
        command_id=req.command_id,
        checkpoint_id=req.checkpoint_id,
        model=req.model,
        context=ctx,
    )
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)
    return {"status": "queued", "thread_id": req.thread_id, "message_id": result.message_id}


@router.post("/chat/stop", response_model=StopChatResponse)
async def stop_chat(req: ChatRequest):
    """
    Stop the current generation for a thread.
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    await activity_monitor.stop_run(req.thread_id)
    return StopChatResponse(status="stopping", thread_id=req.thread_id)


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(req: ChatRequest, bg_tasks: BackgroundTasks, _request: Request = None):
    """
    Retry a specific user message (Targeted Retry).
    Rolls back history (deletes messages after the target) and restarts generation.

    Uses the new event-driven RewindOrchestrator for distributed cleanup.
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.rewind.exceptions import MessageNotFoundError, NoHumanMessageError, RewindError

    # =============================================================================
    # Phase 1: Rewind (Retry-Specific)
    # =============================================================================

    async with session_scope() as session:
        # Determine target message
        if req.message_id:
            logger.info(f"[Retry] Targeted retry for message {req.message_id}")
            stmt = (
                select(Message)
                .options(selectinload(Message.references))
                .where(Message.id == req.message_id)
            )
            result = await session.execute(stmt)
            target_msg = result.scalar_one_or_none()

            if not target_msg:
                logger.warning(f"[Retry] Message {req.message_id} not found in database")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} not found")
            if target_msg.thread_id != req.thread_id:
                logger.warning(f"[Retry] Message {req.message_id} belongs to thread {target_msg.thread_id}, not {req.thread_id}")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} not found in thread")
            if target_msg.role != "human":
                logger.warning(f"[Retry] Message {req.message_id} has role '{target_msg.role}', not 'human'")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} is not a human message")
            last_human_msg = target_msg
        else:
            # Fallback to last human message
            stmt = (
                select(Message)
                .options(selectinload(Message.references))
                .where(Message.thread_id == req.thread_id)
                .where(Message.role == "human")
                .order_by(Message.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            last_human_msg = result.scalar_one_or_none()

        if not last_human_msg:
            raise HTTPException(status_code=404, detail="No human message found to retry")

        # Load attachments for reconstruction
        attachments = None
        if last_human_msg.references:
            attachments = [
                {
                    "type": ref.type,
                    "id": ref.target_id,
                    "name": ref.target_name,
                    "url": ref.target_id if ref.type in ("file", "image") else None,
                }
                for ref in last_human_msg.references
            ]

        retry_message_content = last_human_msg.content

    # Perform Rewind using new event-driven RewindOrchestrator
    try:
        # Create orchestrator on-demand (stateless, lightweight)
        from app.core.events import system_bus
        orchestrator = RewindOrchestrator(event_bus=system_bus)

        # Perform rewind with retry-specific parameters
        result = await orchestrator.perform_rewind(
            thread_id=req.thread_id,
            target_message_id=str(last_human_msg.id),
            include_target=False,  # Retry specific: Keep the human message
            revert_files=req.revert_files,
            reset_state=True,      # Retry specific: Reset state for clean generation
            reason="retry"
        )

        files_reverted = result.reverted_file_count
        # Note: checkpoint_id is not directly available from new orchestrator
        # State reset is handled by StateRewind handler
        checkpoint_id = None

        # Verify rewind success before proceeding with retry
        if result.status != "success":
            errors_str = "; ".join(result.errors)
            error_msg = f"Rewind failed for retry: {errors_str}"
            logger.error(f"[Retry] {error_msg}")
            # Raise RewindError which is caught below to return 500
            from app.core.engine.rewind.exceptions import RewindError
            raise RewindError(error_msg, thread_id=req.thread_id)

        logger.info(f"[Retry] Rewind completed: {result.removed_message_count} messages removed, "
                   f"{result.reverted_file_count} files reverted")

    except MessageNotFoundError:
        raise HTTPException(status_code=404, detail="Target message not found for retry")
    except NoHumanMessageError:
        raise HTTPException(status_code=404, detail="No human message found to retry")
    except RewindError as e:
        logger.error(f"[Retry] Rewind failed: {e}")
        raise HTTPException(500, f"Rewind failed: {e}")
    except Exception as e:
        logger.error(f"[Retry] Unexpected error during rewind: {e}")
        raise HTTPException(500, f"Retry failed: {e}")

    # =============================================================================
    # Phase 2: Unified Dispatch (Shared with Chat)
    # =============================================================================
    # Setup Context
    ctx = EvoContext(
        thread_id=req.thread_id,
        project_id=req.project_id,
        active_model=req.model
    )
    ContextManager.set(ctx)

    # Use unified dispatcher
    # Note: checkpoint_id is None for new event-driven orchestrator
    # State reset is handled by StateRewind handler

    result = await dispatch_agent_run(
        thread_id=req.thread_id,
        message_content=retry_message_content,
        project_id=req.project_id,
        attachments=attachments,
        command_id=req.command_id,
        checkpoint_id=checkpoint_id,
        model=req.model,
        is_retry=True,
        skip_message_persistence=True,
        goal_prefix="Retry: ",
        context=ctx,
    )
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": result.message_id,
        "action": "retry",
        "files_reverted": files_reverted,
    }


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, bg_tasks: BackgroundTasks):
    """
    Resume a paused/interrupted graph execution.
    Used after Human-in-the-Loop interrupts where user provides input.
    """
    graph = get_graph()
    checkpointer = db_resource_manager.checkpointer

    if not graph or not checkpointer:
        raise HTTPException(status_code=500, detail="Graph or Checkpointer not initialized")

    # Config for resuming from checkpoint
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": req.model,
            "run_id": f"run-resume-{gen_uuid()[:8]}",
        }
    }

    # Prepare input - if user provided input, add as message
    inputs = None
    if req.user_input:
        # Check if user_input contains temporary project context (Scheme C)
        try:
            parsed = json.loads(req.user_input)
            if isinstance(parsed, dict) and parsed.get("type") == "temp_project":
                temp_project_id = parsed.get("project_id")
                # Store temporary project for this thread
                thread_context_store.set_temp_project(req.thread_id, temp_project_id)
                # Use empty input for actual resume (the project is now in context)
                # Use system_tools template for selection message
                from app.utils import SystemToolsFormatter
                sel_msg = SystemToolsFormatter.signals([f"Selected project: {parsed.get('project_name', temp_project_id)}"])
                inputs = {"messages": [HumanMessage(content=sel_msg)]}
            else:
                inputs = {"messages": [HumanMessage(content=req.user_input)]}
        except json.JSONDecodeError:
            inputs = {"messages": [HumanMessage(content=req.user_input)]}

        # Persistence (shared with /chat and /retry via dispatch layer)
        from app.core.engine.dispatch import persist_user_message
        await persist_user_message(
            thread_id=req.thread_id,
            content=req.user_input,
            project_id=req.project_id,
            command_id=req.command_id,
        )

    # [HITL Resume Fix]: Check if we need to auto-complete a Tool Call
    pending_tool = await _get_pending_tool_call(graph, config)
    if pending_tool:
        logger.info(f"Auto-completing tool call {pending_tool['name']} on resume")
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content=req.user_input or "APPROVED",  # Default to APPROVED if empty
        )
        if inputs and "messages" in inputs:
            # Use ToolMessage INSTEAD of HumanMessage
            # Because HumanMessage would confuse the LLM expecting tool output
            inputs["messages"] = [tool_msg]
        else:
            inputs = {"messages": [tool_msg]}

    # Resume in background (unified resumption loop)
    bg_tasks.add_task(
        resume_graph_background,
        req.thread_id,
        inputs,
        config,
        run_label="Resuming...",
        clear_human_request_flag=True,
    )

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)


@router.post("/hitl/cancel")
async def cancel_hitl_request(req: CancelHITLRequest, bg_tasks: BackgroundTasks):
    """
    Cancel a pending HITL (Human-in-the-Loop) request.
    This will dismiss the confirmation card and resume execution with a cancellation signal.
    """
    from app.domain.tools.human_input import cancel_request, get_pending_requests_for_thread
    from app.infrastructure.database.resource_manager import db_resource_manager

    graph = get_graph()
    checkpointer = db_resource_manager.checkpointer

    if not graph or not checkpointer:
        raise HTTPException(
            status_code=500, detail="Graph or Checkpointer not initialized"
        )

    # Find pending HITL request for this thread
    pending_requests = await get_pending_requests_for_thread(req.thread_id)

    # [HITL 404 Fix]: Also check activity monitor for transient requests (like project switch)
    activity_state = await activity_monitor._state_service.get_state(req.thread_id)
    has_activity_request = activity_state.get("human_request") is not None

    if not pending_requests and not has_activity_request:
        raise HTTPException(
            status_code=404, detail="No pending HITL request found for this thread"
        )

    # If it's a DB-backed request, cancel it there first
    request_to_cancel = None
    if pending_requests:
        # Cancel the most recent pending request
        request_to_cancel = pending_requests[-1]
        cancel_success = await cancel_request(request_to_cancel.id)

        if not cancel_success:
            raise HTTPException(
                status_code=500, detail="Failed to cancel HITL request"
            )

    # Always clear the human request from activity monitor
    await activity_monitor.clear_human_request(req.thread_id)

    # If this was purely a transient activity request (no DB record), we're done
    # No need to resume the graph as transient requests don't pause it with a checkpoint
    if not pending_requests:
        return CancelHITLResponse(
            status="cancelled",
            thread_id=req.thread_id,
            request_id=None,
        )

    # Config for resuming from checkpoint
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": req.model,
            "run_id": f"run-cancel-{gen_uuid()[:8]}",
        }
    }

    # Prepare cancellation response
    cancel_reason = req.reason or "User cancelled the request"

    # [HITL Cancel Fix]: Send cancellation as ToolMessage instead of HumanMessage
    pending_tool = await _get_pending_tool_call(graph, config)
    if pending_tool:
        logger.info(f"Auto-cancelling tool call {pending_tool['name']} on cancel")
        # Use default_value from DB request if it exists, else "CANCELLED"
        cancel_response = request_to_cancel.default_value or "CANCELLED"
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content=cancel_response,
        )
        inputs = {"messages": [tool_msg]}
    else:
        inputs = {"messages": [HumanMessage(content=f"Request cancelled: {cancel_reason}")]}

    # Resume in background with cancellation signal (unified resumption loop)
    bg_tasks.add_task(
        resume_graph_background,
        req.thread_id,
        inputs,
        config,
        run_label="Resuming after cancellation...",
    )

    return CancelHITLResponse(
        status="cancelled",
        thread_id=req.thread_id,
        request_id=request_to_cancel.id if request_to_cancel else None,
    )


@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest, bg_tasks: BackgroundTasks):
    """
    Entry point for External Events (Local BG Task).
    """
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload.model_dump())
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")

    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    ctx = EvoContext(thread_id=tid)
    ContextManager.set(ctx)

    if req.event_type == "project_switched":
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            # CRITICAL: Invalidate project cache to prevent stale path overwrite
            # Background: _setup_project_context() in background_agent.py calls
            # evocloud_manager.get_project_by_id() which uses 60s TTL cache.
            # Without invalidation, the cache may return old path and overwrite
            # the new_path we just set here, causing Agent to operate on wrong directory.
            evocloud_manager.invalidate_projects_cache()
            logger.info("[Webhook] Project cache invalidated due to project_switched event")

            thread_context_store.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed

            repo_name = os.path.basename(new_path)

            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return WebhookResponse(status="switched", thread_id=tid)

    # Use Unified Dispatcher
    result = await dispatch_agent_run(
        thread_id=tid,
        message_content=messages[0].content if messages else "No content",
        project_id=1,  # Default project
        goal_prefix=f"[{req.source.capitalize()} Event] ",
    )

    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, tid, result.inputs)

    return WebhookResponse(status="accepted", thread_id=tid)
