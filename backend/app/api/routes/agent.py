import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUserOptional, verify_guest_access
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
from app.models import (
    Conversation,
    Message,
    MessageReference,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str
    message: str
    project_id: int | None = 1
    command_id: int | None = None
    checkpoint_id: str | None = None
    attachments: list[dict[str, Any]] | None = None  # [{"url": "...", "type": "image"}]
    revert_files: bool = True  # For retry/undo support


class WebhookRequest(BaseModel):
    source: str
    event_type: str
    payload: dict[str, Any]
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    user_input: str | None = None  # Optional user response for HITL
    command_id: int | None = None  # Explicit command_id for resumption trace


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
    goal = message_content[:50] + "..." if len(message_content) > 50 else message_content
    if attachments:
        goal = f"[Image] {goal}"
    if goal_prefix:
        goal = f"{goal_prefix}{goal}"

    await activity_monitor.start_run(thread_id, goal)

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

                logger.info(f"[Dispatch] Persisted user message for {thread_id} (seq={user_msg.sequence_number})")

                # Persist References
                if attachments:
                    for att in attachments:
                        ref_type = att.get("type", "file")
                        target_id = att.get("url") or att.get("id") or "unknown"
                        target_name = att.get("name") or target_id

                        ref = MessageReference(
                            id=str(uuid.uuid4()),
                            message_id=user_msg.id,
                            type=ref_type,
                            target_id=str(target_id),
                            target_name=str(target_name),
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
    if is_retry:
        # Retry: Don't include messages in inputs, checkpoint already has them
        inputs = {
            "project_id": project_id,
            "checkpoint_id": checkpoint_id,
            "is_retry": True,
            "goal": goal,
        }
    else:
        # New chat: Include messages for LangGraph
        messages = [{"type": "human", "content": content_blocks}]
        inputs = {
            "messages": messages,
            "project_id": project_id,
            "checkpoint_id": checkpoint_id,
            "is_retry": False,
            "goal": goal,
        }

    bg_tasks.add_task(run_agent_background, thread_id, inputs)

    result = {"status": "queued", "thread_id": thread_id}
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

    # Use Unified Dispatcher
    return await _prepare_and_dispatch(
        thread_id=req.thread_id,
        project_id=req.project_id,
        bg_tasks=bg_tasks,
        message_content=req.message,
        attachments=req.attachments,
        command_id=req.command_id,
        checkpoint_id=req.checkpoint_id,
        is_retry=False,
    )


@router.post("/chat/stop")
async def stop_chat(req: ChatRequest):
    """
    Stop the current generation for a thread.
    """
    await activity_monitor.stop_run(req.thread_id)
    return {"status": "stopping", "thread_id": req.thread_id}


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(req: ChatRequest, bg_tasks: BackgroundTasks):
    """
    Retry the last user message.
    Rolls back history (deletes AI messages after last human msg) and restarts generation.

    Refactored to use unified dispatch logic after rewind.
    """
    from app.core.engine.history import history_service

    # =============================================================================
    # Phase 1: Rewind (Retry-Specific)
    # =============================================================================
    from sqlalchemy.orm import selectinload

    async with session_scope() as session:
        # Find last human message BEFORE rewinding (eager load references)
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

        # Load attachments for reconstruction (inside session)
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

    # Perform Rewind (HistoryService handles DB, LangGraph and Files)
    try:
        rewind_result = await history_service.perform_rewind(
            thread_id=req.thread_id,
            target_message_id=str(last_human_msg.id),
            revert_files=req.revert_files,
            include_target=False  # Keep the human message in DB and Graph
        )
        files_reverted = rewind_result.get("files_reverted", 0)
    except Exception as e:
        logger.error(f"History rewind failed during retry: {e}")
        raise HTTPException(500, f"History rollback failed: {e}")

    # =============================================================================
    # Phase 2: Unified Dispatch (Shared with Chat)
    # =============================================================================
    # Setup Context
    ctx = EvoContext(thread_id=req.thread_id, project_id=req.project_id)
    ContextManager.set(ctx)

    # Use unified dispatcher
    # Retry should NOT pass checkpoint_id - it must start from the latest state after rewind
    result = await _prepare_and_dispatch(
        thread_id=req.thread_id,
        project_id=req.project_id,
        bg_tasks=bg_tasks,
        message_content=retry_message_content,
        attachments=attachments,
        command_id=req.command_id,
        checkpoint_id=None,  # Retry always starts from latest checkpoint after rewind
        goal_prefix="Retry: ",
        is_retry=True,
        skip_message_persistence=True,
    )

    result["files_reverted"] = files_reverted
    return result


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, bg_tasks: BackgroundTasks):
    """
    Resume a paused/interrupted graph execution.
    Used after Human-in-the-Loop interrupts where user provides input.
    """
    from langchain_core.messages import HumanMessage

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
                inputs = {"messages": [HumanMessage(content=f"Selected project: {parsed.get('project_name', temp_project_id)}")]}
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
            # Tool has already updated Redis state, so we just end cleanly.
            # DO NOT mark as 'failed' in activity_monitor.
            logger.info(f"Resume interrupted for human input: {req.thread_id}")
        except Exception as e:
            logger.error(f"Resume error for {req.thread_id}: {e}")
            await activity_monitor.end_run(req.thread_id, "failed")

    bg_tasks.add_task(_resume_graph)

    return {"status": "resuming", "thread_id": req.thread_id}


@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest, bg_tasks: BackgroundTasks):
    """
    Entry point for External Events (Local BG Task).
    """
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload)
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")

    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    ctx = EvoContext(thread_id=tid)
    ContextManager.set(ctx)

    if req.event_type == "project_switched":
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            thread_context_store.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed

            repo_name = os.path.basename(new_path)

            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return {"status": "switched", "thread_id": tid, "path": new_path}

    # Serialization for Webhook messages
    serialized_msgs = []
    for m in messages:
        if isinstance(m, HumanMessage):
            serialized_msgs.append({"type": "human", "content": m.content})
        else:
            serialized_msgs.append({"type": "human", "content": str(m.content)})

    inputs = {"messages": serialized_msgs}

    bg_tasks.add_task(run_agent_background, tid, inputs)

    return {"status": "accepted", "thread_id": tid}
