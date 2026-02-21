import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel
from sqlalchemy import func, select

from app.domain.integration.adapters import EventAdapter
from app.api.deps import CurrentUserOptional, verify_guest_access

# --- Background Worker ---
from app.core.engine.background_agent import run_agent_background
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.core.context import thread_context_store
from app.infrastructure.database.sql.database import session_scope
from app.models import (
    Conversation,
    Message,
    MessageReference,
)
from app.core.evocloud import evocloud_manager
from app.core.context.manager import ContextManager, EvoContext

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Models ---


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


# --- Endpoints ---


@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(
    req: ChatRequest,
    bg_tasks: BackgroundTasks,  # Injected
    _current_user: CurrentUserOptional,  # Used for context if needed, though verified by deps
):
    """
    Unified entry point for User Chat (Local Background Task).
    Guest Verification is handled by 'verify_guest_access' dependency.
    """
    # Initialize Context for Request (so reference service can use it if needed, though mostly for background task)
    # Background task will re-initialize its own context.
    # But we might need it here for logging or sync operations.
    ctx = EvoContext(
        request_id=f"req-{req.thread_id}-{int(time.time())}",
        thread_id=req.thread_id,
        project_id=req.project_id,
        command_id=req.command_id
    )
    ContextManager.set(ctx)

    # --- Context Injection & Message Construction (Phase 9) ---
    from app.domain.project.reference_service import reference_service
    
    async with session_scope() as session:
        ref_context = await reference_service.process_references(
            message_text=req.message,
            attachments=req.attachments or [],
            session=session,
            project_id=req.project_id
        )
    
    content_blocks = ref_context.content_blocks
    reference_notes = ref_context.reference_notes

    # Final LangChain message format
    messages = [{"type": "human", "content": content_blocks}]

    inputs = {
        "messages": messages,
        "project_id": req.project_id,
        "checkpoint_id": req.checkpoint_id,
    }

    # Enable monitor
    goal = req.message[:50] + "..." if len(req.message) > 50 else req.message
    if req.attachments:
        goal = f"[Image] {goal}"
    await activity_monitor.start_run(req.thread_id, goal)

    # 3. Upsert Conversation Record
    try:
        async with session_scope() as session:
            conversation = await session.get(Conversation, req.thread_id)
            if not conversation:
                conversation = Conversation(
                    id=req.thread_id,
                    project_id=req.project_id,
                    title=req.message[:50],
                )
                session.add(conversation)
            else:
                conversation.updated_at = datetime.now(timezone.utc)

            # 4. Upsert User Message with Correct Sequence
            # We need to find the next sequence number (max + 1) to maintain order
            stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == req.thread_id)
            max_seq = (await session.execute(stmt)).scalar() or 0

            user_msg = Message(
                thread_id=req.thread_id,
                project_id=req.project_id,
                role="human",
                content=req.message,
                thinking=None,
                sequence_number=max_seq + 1,
            )
            session.add(user_msg)
            await session.flush()  # Ensure FK consistency
            logger.info(f"Persisted user message for thread {req.thread_id} (seq={user_msg.sequence_number})")

            # 4.5 Sync to EvoCloud (Device Logs + Chat Stream)
            try:
                await evocloud_manager.upload_log(
                    thread_id=req.thread_id,
                    log_type="user",
                    content=req.message,
                    project_id=req.project_id,
                    command_id=req.command_id
                )
            except Exception as sync_e:
                logger.warning(f"Failed to sync human message to cloud: {sync_e}")

            # 5. Upsert References (Phase 9)
            if req.attachments:
                for att in req.attachments:
                    # att structure: {type: 'file'|'image'|'message', url?: string, id?: string, name?: string}
                    ref_type = att.get("type", "file")
                    target_id = att.get("url") or att.get("id") or "unknown"
                    target_name = att.get("name") or target_id

                    # Special handling for message references
                    if ref_type == "message":
                        pass

                    ref = MessageReference(
                        id=str(uuid.uuid4()),
                        message_id=user_msg.id,
                        type=ref_type,
                        target_id=str(target_id),
                        target_name=str(target_name),
                    )
                    session.add(ref)

                logger.info(f"Persisted {len(req.attachments)} references for msg {user_msg.id}")

    except Exception as e:
        logger.error(f"Failed to upsert logic: {e}")
        # Phase 18 Fix: Do not silence DB errors. If persistence fails, the user needs to know.
        raise HTTPException(status_code=500, detail=f"Failed to save message: {str(e)}")

    # 2. Dispatch Background Task (Local)
    bg_tasks.add_task(run_agent_background, req.thread_id, inputs)

    return {"status": "queued", "thread_id": req.thread_id}


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
    """
    from app.core.engine.history import history_service
    from app.infrastructure.database.sql.database import session_scope

    retry_message_content = None

    async with session_scope() as session:
        # 1. Find last human message BEFORE rewinding
        stmt = (
            select(Message)
            .where(Message.thread_id == req.thread_id)
            .where(Message.role == "human")
            .order_by(Message.id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last_human_msg = result.scalar_one_or_none()

        if not last_human_msg:
            raise HTTPException(status_code=404, detail="No human message found to retry")

        retry_message_content = last_human_msg.content

    # 2. Perform Rewind (HistoryService handles DB, LangGraph and Files)
    try:
        rewind_result = await history_service.perform_rewind(
            thread_id=req.thread_id,
            revert_files=req.revert_files
        )
        files_reverted = rewind_result.get("files_reverted", 0)
    except Exception as e:
        logger.error(f"History rewind failed during retry: {e}")
        raise HTTPException(500, f"History rollback failed: {e}")

    # 3. Setup Context
    ctx = EvoContext(thread_id=req.thread_id, project_id=req.project_id)
    ContextManager.set(ctx)
    await activity_monitor.start_run(
        req.thread_id, f"Retry: {retry_message_content[:50]}..."
    )

    # 4. Dispatch
    # Ensure inputs match normal chat flow
    inputs = {
        "messages": [{"type": "human", "content": retry_message_content}],
        "project_id": req.project_id,
        "is_retry": True,  # Flag for engine if needed (optional)
    }

    bg_tasks.add_task(run_agent_background, req.thread_id, inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "action": "retry",
        "files_reverted": files_reverted
    }


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
