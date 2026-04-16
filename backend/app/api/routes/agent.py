import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUserOptional,
    verify_guest_access,
)
from app.api.responses import BaseAPIResponse
from app.constants import DEFAULT_PROJECT_ID
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext
# --- Background Worker ---
from app.core.engine.background_agent import run_agent_background
from app.core.evocloud import evocloud_manager
from app.core.exceptions import AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.domain.integration.adapters import EventAdapter
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import (
    Conversation,
    Message,
    MessageReference,
)
from app.models.learning import LearnedSkill
from app.models.schemas.base import ScopedRequest

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(ScopedRequest):
    thread_id: str
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


class CancelHITLRequest(ScopedRequest):
    thread_id: str
    reason: str | None = None  # Optional reason for cancellation


# =============================================================================
# Unified Dispatch Helpers
# =============================================================================

async def _prepare_and_dispatch(
    thread_id: str,
    project_id: int,
    bg_tasks: BackgroundTasks,
    message_content: str,
    attachments: list[dict[str, Any]] | None = None,
    command_id: int | None = None,
    checkpoint_id: str | None = None,
    goal_prefix: str = "",
    is_retry: bool = False,
    skip_message_persistence: bool = False,
    model: str | None = None,
) -> dict:
    """
    Unified dispatcher for Agent runs (Chat & Retry).

    Args:
        skip_message_persistence: For Retry, when message already exists in DB.

    Returns: {"status": "queued", "thread_id": thread_id, ...}
    """
    # --- 1. Process References (Phase 9) ---
    from app.domain.project.reference_service import reference_service

    async with session_scope() as session:
        ref_context = await reference_service.process_references(
            message_text=message_content,
            attachments=attachments or [],
            session=session,
            project_id=project_id
        )

    content_blocks = ref_context.content_blocks

    # --- 2. Build Goal for Activity Monitor ---
    goal = message_content[:200] + "..." if len(message_content) > 200 else message_content
    if attachments:
        goal = f"[Image] {goal}"
    if goal_prefix:
        goal = f"{goal_prefix}{goal}"

    await activity_monitor.start_run(thread_id, goal)

    persisted_msg_id = None

    # --- 3. DB Persistence & EvoCloud Sync ---
    try:
        async with session_scope() as session:
            # Upsert Conversation (always update timestamp)
            conversation = await session.get(Conversation, thread_id)
            if not conversation:
                conversation = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=message_content[:50],
                )
                session.add(conversation)
            else:
                conversation.updated_at = datetime.now(timezone.utc)

            if not skip_message_persistence:
                # New message: persist to DB
                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == thread_id)
                max_seq = (await session.execute(stmt)).scalar() or 0

                user_msg = Message(
                    thread_id=thread_id,
                    project_id=project_id,
                    role="human",
                    content=message_content,
                    thinking=None,
                    sequence_number=max_seq + 1,
                )
                session.add(user_msg)
                await session.flush()
                persisted_msg_id = user_msg.id

                logger.info(f"[Dispatch] Persisted user message for {thread_id} (seq={user_msg.sequence_number})")

                # Persist References
                if attachments:
                    for att in attachments:
                        ref_type = att.get("type", "file")
                        target_id = att.get("url") or att.get("id") or "unknown"
                        target_name = att.get("name") or target_id
                        metadata = att.get("metadata")  # Extract metadata for audio, images, etc.

                        ref = MessageReference(
                            id=str(uuid.uuid4()),
                            message_id=user_msg.id,
                            type=ref_type,
                            target_id=str(target_id),
                            target_name=str(target_name),
                            metadata=metadata,
                        )
                        session.add(ref)

                    logger.info(f"[Dispatch] Persisted {len(attachments)} references for msg {user_msg.id}")
            else:
                logger.info(f"[Dispatch] Skipped persistence for retry (message already exists)")

        # Sync to EvoCloud (outside transaction)
        try:
            await evocloud_manager.upload_log(
                thread_id=thread_id,
                log_type="user",
                content=message_content,
                project_id=project_id,
                command_id=command_id
            )
        except Exception as sync_e:
            logger.warning(f"[Dispatch] Failed to sync to EvoCloud: {sync_e}")

    except Exception as e:
        logger.error(f"[Dispatch] Failed to persist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save message: {str(e)}")

    # --- 4. Build Inputs & Dispatch ---
    # CRITICAL FIX: Always include messages in inputs to ensure correct content is used.
    # For retry, we must pass the target message content because the checkpoint may not
    # have the latest message state (it was saved before the target message was processed).
    messages = [{"type": "human", "content": content_blocks}]
    inputs = {
        "messages": messages,
        "project_id": project_id,
        "checkpoint_id": checkpoint_id,
        "is_retry": is_retry,
        "goal": goal,
        "session_goal": message_content.strip(),  # Persistent session-level goal for agent state
        "model": model,  # Pass user selected model
    }

    bg_tasks.add_task(run_agent_background, thread_id, inputs)

    result = {"status": "queued", "thread_id": thread_id}
    if persisted_msg_id is not None:
        result["message_id"] = persisted_msg_id
    if is_retry:
        result["action"] = "retry"
    return result


@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(
    req: ChatRequest,
    bg_tasks: BackgroundTasks,
    _current_user: CurrentUserOptional,
):
    """
    Unified entry point for User Chat (Local Background Task).
    """
    # Initialize Context for Request
    ctx = EvoContext(
        request_id=f"req-{req.thread_id}-{int(time.time())}",
        thread_id=req.thread_id,
        project_id=req.project_id,
        command_id=req.command_id
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

    # ==========================================================================
    # OPTIMIZATION: Predictive Memory Loading
    # Start background task to pre-load semantic search results from Neo4j.
    # This runs in parallel with LangGraph initialization (~100ms), effectively
    # hiding the ~800ms Neo4j query latency.
    # ==========================================================================
    from app.core.memory.predictive_loader import predictive_memory_load
    
    run_id = f"run-{req.thread_id}-{int(time.time())}"
    bg_tasks.add_task(
        predictive_memory_load,
        thread_id=req.thread_id,
        project_id=req.project_id or DEFAULT_PROJECT_ID,
        human_message=req.message,
        run_id=run_id
    )
    logger.debug(f"[ChatEndpoint] Spawned predictive memory loading for thread {req.thread_id}")

    # Use Unified Dispatcher
    return await _prepare_and_dispatch(
        thread_id=req.thread_id,
        project_id=req.project_id,
        bg_tasks=bg_tasks,
        message_content=req.message,
        attachments=attachments,
        command_id=req.command_id,
        checkpoint_id=req.checkpoint_id,
        is_retry=False,
        model=req.model,  # Pass user selected model
    )


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


@router.post("/chat/stop", response_model=StopChatResponse)
async def stop_chat(req: ChatRequest):
    """
    Stop the current generation for a thread.
    """
    await activity_monitor.stop_run(req.thread_id)
    return StopChatResponse(status="stopping", thread_id=req.thread_id)


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(
    req: ChatRequest, 
    bg_tasks: BackgroundTasks,
    request: Request = None
):
    """
    Retry a specific user message (Targeted Retry).
    Rolls back history (deletes messages after the target) and restarts generation.
    
    Uses the new event-driven RewindOrchestrator for distributed cleanup.
    """
    from app.core.checkpoint.rewind import RewindOrchestrator
    from app.core.checkpoint.rewind.exceptions import (
        MessageNotFoundError,
        NoHumanMessageError,
        RewindError
    )
    from sqlalchemy.orm import selectinload

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
            from app.core.checkpoint.rewind.exceptions import RewindError
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
    ctx = EvoContext(thread_id=req.thread_id, project_id=req.project_id)
    ContextManager.set(ctx)

    # Use unified dispatcher
    # Note: checkpoint_id is None for new event-driven orchestrator
    # State reset is handled by StateRewind handler

    dispatch_result = await _prepare_and_dispatch(
        thread_id=req.thread_id,
        project_id=req.project_id,
        bg_tasks=bg_tasks,
        message_content=retry_message_content,
        attachments=attachments,
        command_id=req.command_id,
        checkpoint_id=checkpoint_id,
        goal_prefix="Retry: ",
        is_retry=True,
        skip_message_persistence=True,
        model=req.model,  # Pass user selected model (if any)
    )

    dispatch_result["files_reverted"] = files_reverted
    return dispatch_result


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, bg_tasks: BackgroundTasks):
    """
    Resume a paused/interrupted graph execution.
    Used after Human-in-the-Loop interrupts where user provides input.
    """
    from app.core.globals import get_graph
    from app.core.persistence import get_checkpointer

    graph = get_graph()
    checkpointer = get_checkpointer()

    if not graph or not checkpointer:
        raise HTTPException(
            status_code=500, detail="Graph or Checkpointer not initialized"
        )

    # Config for resuming from checkpoint
    config = {
        "configurable": {
            "thread_id": req.thread_id
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

        # PERSISTENCE FIX: Save user confirmation to history
        try:
            async with session_scope() as session:
                conversation = await session.get(Conversation, req.thread_id)
                if conversation:
                    conversation.updated_at = datetime.now(timezone.utc)

                    # We need to find the next sequence number (max + 1)
                    # For simplicity/speed, we might skip sequence check or query it.
                    # Given sequence_number is mapped but not strict, we can default or query.
                    # Let's do a quick query for correctness.
                    stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == req.thread_id)
                    max_seq = (await session.execute(stmt)).scalar() or 0

                    user_msg = Message(
                        thread_id=req.thread_id,
                        project_id=conversation.project_id,
                        role="human",
                        content=req.user_input,
                        sequence_number=max_seq + 1,
                    )
                    session.add(user_msg)
                    logger.info(f"Persisted RESUME message for thread {req.thread_id}")

                    # Sync to EvoCloud (Logs + Chat Stream)
                    try:
                        command_id = req.command_id or ContextManager.current().command_id
                        await evocloud_manager.upload_log(
                            thread_id=req.thread_id,
                            log_type="user",
                            content=req.user_input,
                            project_id=conversation.project_id,
                            command_id=command_id
                        )
                    except Exception as sync_e:
                        logger.warning(f"Failed to sync resume message to cloud: {sync_e}")
        except Exception as e:
            logger.error(f"Failed to persist resume message: {e}")
            # Non-blocking, continue resume flow

    # [HITL Resume Fix]: Check if we need to auto-complete a Tool Call
    try:
        current_state = await graph.aget_state(config)
        if current_state.values and "messages" in current_state.values:
            history = current_state.values["messages"]
            if history:
                last_msg = history[-1]
                # If last message was an Assistant Message with tool_calls (pending)
                # AND there are no corresponding ToolMessages yet
                # We should inject a ToolMessage representing the human approval
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    # Check if it was "request_approval" or "request_human_input"
                    last_tool_call = last_msg.tool_calls[-1]
                    if last_tool_call["name"] in ["request_approval", "request_human_input"]:
                        logger.info(f"Auto-completing tool call {last_tool_call['name']} on resume")
                        tool_msg = ToolMessage(
                            tool_call_id=last_tool_call["id"],
                            content=req.user_input
                            or "APPROVED",  # Default to APPROVED if empty for approval
                        )

                        if inputs:
                            if "messages" in inputs:
                                # Prepend or Replace? Use ToolMessage INSTEAD of HumanMessage
                                # Because HumanMessage would confuse the LLM expecting tool output
                                inputs["messages"] = [tool_msg]
                            else:
                                inputs["messages"] = [tool_msg]
                        else:
                            inputs = {"messages": [tool_msg]}
    except Exception as state_e:
        logger.warning(f"Failed to inspect state for smart resume: {state_e}")

    # Resume in background
    async def _resume_graph():
        from app.core.callbacks.transparent import TransparentCallbackHandler
        from app.core.exceptions import AgentCancelledException

        callback = TransparentCallbackHandler(thread_id=req.thread_id)

        try:
            # Clear any pending human request since we are resuming
            await activity_monitor.clear_human_request(req.thread_id)
            await activity_monitor.start_run(req.thread_id, "Resuming...")

            resume_config = {
                **config,
                "callbacks": [callback]
            }

            # Resume execution
            async for _event in graph.astream(inputs, config=resume_config):
                await activity_monitor.check_cancellation(req.thread_id)

            await activity_monitor.end_run(req.thread_id, "done")

        except AgentCancelledException:
            await activity_monitor.end_run(req.thread_id, "cancelled")
        except AgentHumanInterruptException:
            # INTERRUPT: Task interrupted for human input.
            # Tool has already updated cache state, so we just end cleanly.
            # DO NOT mark as 'failed' in activity_monitor.
            logger.info(f"Resume interrupted for human input: {req.thread_id}")
        except Exception as e:
            logger.error(f"Resume error for {req.thread_id}: {e}")
            await activity_monitor.end_run(req.thread_id, "failed")

    bg_tasks.add_task(_resume_graph)

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)


@router.post("/hitl/cancel")
async def cancel_hitl_request(req: CancelHITLRequest, bg_tasks: BackgroundTasks):
    """
    Cancel a pending HITL (Human-in-the-Loop) request.
    This will dismiss the confirmation card and resume execution with a cancellation signal.
    """
    from app.core.globals import get_graph
    from app.core.persistence import get_checkpointer
    from app.domain.tools.human_input import (
        cancel_request,
        get_pending_requests_for_thread,
    )

    graph = get_graph()
    checkpointer = get_checkpointer()

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
            "thread_id": req.thread_id
        }
    }

    # Prepare cancellation response
    cancel_reason = req.reason or "User cancelled the request"

    # [HITL Cancel Fix]: Send cancellation as ToolMessage instead of HumanMessage
    # This ensures the graph recognizes the tool call as completed.
    try:
        current_state = await graph.aget_state(config)
        if current_state.values and "messages" in current_state.values:
            history = current_state.values["messages"]
            if history:
                last_msg = history[-1]
                # If last message was an Assistant Message with tool_calls (pending)
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    last_tool_call = last_msg.tool_calls[-1]
                    if last_tool_call["name"] in ["request_approval", "request_human_input"]:
                        logger.info(f"Auto-cancelling tool call {last_tool_call['name']} on cancel")

                        # Use default_value from DB request if it exists, else "CANCELLED"
                        cancel_response = request_to_cancel.default_value or "CANCELLED"

                        tool_msg = ToolMessage(
                            tool_call_id=last_tool_call["id"],
                            content=cancel_response,
                        )
                        inputs = {"messages": [tool_msg]}
                    else:
                        inputs = {"messages": [HumanMessage(content=f"Request cancelled: {cancel_reason}")]}
                else:
                    inputs = {"messages": [HumanMessage(content=f"Request cancelled: {cancel_reason}")]}
    except Exception as state_e:
        logger.warning(f"Failed to inspect state for cancel: {state_e}")
        inputs = {"messages": [HumanMessage(content=f"Request cancelled: {cancel_reason}")]}

    # Resume in background with cancellation signal
    async def _cancel_and_resume():
        from app.core.callbacks.transparent import TransparentCallbackHandler
        from app.core.exceptions import AgentCancelledException

        callback = TransparentCallbackHandler(thread_id=req.thread_id)

        try:
            await activity_monitor.start_run(req.thread_id, "Resuming after cancellation...")

            resume_config = {
                **config,
                "callbacks": [callback]
            }

            # Resume execution with cancellation signal
            async for _event in graph.astream(inputs, config=resume_config):
                await activity_monitor.check_cancellation(req.thread_id)

            await activity_monitor.end_run(req.thread_id, "done")

        except AgentCancelledException:
            await activity_monitor.end_run(req.thread_id, "cancelled")
        except AgentHumanInterruptException:
            logger.info(f"Cancel interrupted for human input: {req.thread_id}")
        except Exception as e:
            logger.error(f"Cancel resume error for {req.thread_id}: {e}")
            await activity_monitor.end_run(req.thread_id, "failed")

    bg_tasks.add_task(_cancel_and_resume)

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
            logger.info(f"[Webhook] Project cache invalidated due to project_switched event")

            thread_context_store.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed

            repo_name = os.path.basename(new_path)

            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return WebhookResponse(status="switched", thread_id=tid)

    # Serialization for Webhook messages
    serialized_msgs = []
    for m in messages:
        if isinstance(m, HumanMessage):
            serialized_msgs.append({"type": "human", "content": m.content})
        else:
            serialized_msgs.append({"type": "human", "content": str(m.content)})

    inputs = {"messages": serialized_msgs}

    bg_tasks.add_task(run_agent_background, tid, inputs)

    return WebhookResponse(status="accepted", thread_id=tid)
