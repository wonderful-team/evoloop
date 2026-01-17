from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.adapters import EventAdapter
from app.api.deps import CurrentUserOptional, verify_guest_access

# --- Background Worker ---
from app.core.engine.tasks import run_agent_background
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Conversation, Message, MessageReference
from app.logging import logger, set_context

router = APIRouter()

# --- Models ---

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    project_id: int | None = 1
    checkpoint_id: str | None = None
    attachments: list[dict[str, Any]] | None = None # [{"url": "...", "type": "image"}]

class WebhookRequest(BaseModel):
    source: str
    event_type: str
    payload: dict[str, Any]
    thread_id: str | None = None

# --- Endpoints ---

@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(
    req: ChatRequest,
    bg_tasks: BackgroundTasks, # Injected
    current_user: CurrentUserOptional, # Used for context if needed, though verified by deps
    x_guest_id: Annotated[str | None, Header()] = None
):
    """
    Unified entry point for User Chat (Local Background Task).
    Guest Verification is handled by 'verify_guest_access' dependency.
    """
    set_context(thread_id=req.thread_id, project_id=req.project_id)

    # 0. Context Injection (Phase 9)
    # If referencing messages, fetch content and append to input
    if req.attachments:
        try:
            from app.infrastructure.database.sql.database import session_scope
            from app.infrastructure.database.sql.models import Message
            async with session_scope() as session:
                for att in req.attachments:
                    if att.get("type") == "message" and att.get("id"):
                         # Fetch message content
                         try:
                             msg_id = int(att["id"])
                             ref_msg = await session.get(Message, msg_id)
                             if ref_msg and ref_msg.content:
                                 # Append to user message for context
                                 # Use XML-like quoting or Markdown blockquote
                                 snippet = ref_msg.content[:500] + "..." if len(ref_msg.content) > 500 else ref_msg.content
                                 req.message += f"\n\n> Quoted Message ({att.get('name', 'Reference')}):\n{snippet}\n"
                         except (ValueError, TypeError):
                             logger.warning(f"Invalid message reference ID: {att.get('id')}")
                             continue
        except Exception as e:
            logger.warning(f"Failed to inject reference context: {e}")

    # 1. Construct input state
    if req.attachments:
        # Multimodal Message Construction
        content_blocks = []

        for att in req.attachments:
            if "url" in att:
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": att["url"]}
                })

        # Add text block
        if req.message:
            content_blocks.append({
                "type": "text",
                "text": req.message
            })

        messages = [{"type": "human", "content": content_blocks}]
    else:
        # Standard Text Message
        messages = [{"type": "human", "content": req.message}]

    inputs = {
        "messages": messages,
        "project_id": req.project_id,
        "checkpoint_id": req.checkpoint_id
    }

    # Enable monitor
    goal = req.message[:50] + "..." if len(req.message) > 50 else req.message
    if req.attachments:
        goal = f"[Image] {goal}"
    await activity_monitor.start_run(req.thread_id, goal)

    # 3. Upsert Conversation Record
    try:
        from datetime import datetime, timezone
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

            # Log User Message (sequence_number=1 for first message in each run)
            user_msg = Message(
                thread_id=req.thread_id,
                project_id=req.project_id,
                role="human",
                content=req.message,
                thinking=None,
                sequence_number=1
            )
            session.add(user_msg)
            await session.flush() # Ensure FK consistency
            logger.info(f"Persisted user message for thread {req.thread_id}")

            # 4. Upsert References (Phase 9)
            if req.attachments:
                import uuid
                for att in req.attachments:
                    # att structure: {type: 'file'|'image'|'message', url?: string, id?: string, name?: string}
                    ref_type = att.get("type", "file")
                    target_id = att.get("url") or att.get("id") or "unknown"
                    target_name = att.get("name") or target_id
                    
                    # Special handling for message references
                    if ref_type == 'message':
                        # target_id should be the message ID
                        pass

                    ref = MessageReference(
                        id=str(uuid.uuid4()),
                        message_id=user_msg.id,
                        type=ref_type,
                        target_id=str(target_id),
                        target_name=str(target_name)
                    )
                    session.add(ref)
                
                logger.info(f"Persisted {len(req.attachments)} references for msg {user_msg.id}")

    except Exception as e:
        logger.error(f"Failed to upsert logic: {e}")
        pass

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
async def retry_chat(
    req: ChatRequest,
    bg_tasks: BackgroundTasks
):
    """
    Retry the last user message.
    Rolls back history (deletes AI messages after last human msg) and restarts generation.
    """
    from sqlalchemy import delete, select

    retry_message_content = None

    async with session_scope() as session:
        # 1. Find last human message
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
        last_msg_id = last_human_msg.id

        # 2. Delete all messages AFTER this human message
        del_stmt = (
            delete(Message)
            .where(Message.thread_id == req.thread_id)
            .where(Message.id > last_msg_id)
        )
        await session.execute(del_stmt)
        # Session commits automatically on exit context if no error

        logger.info(f"Retrying thread {req.thread_id} from message {last_msg_id}")

    # 3. Setup Context
    set_context(thread_id=req.thread_id, project_id=req.project_id)
    await activity_monitor.start_run(req.thread_id, f"Retry: {retry_message_content[:50]}...")

    # 4. Dispatch
    # Ensure inputs match normal chat flow
    inputs = {
        "messages": [{"type": "human", "content": retry_message_content}],
        "project_id": req.project_id,
        "is_retry": True # Flag for engine if needed (optional)
    }

    bg_tasks.add_task(run_agent_background, req.thread_id, inputs)

    return {"status": "queued", "thread_id": req.thread_id, "action": "retry"}


class ResumeRequest(BaseModel):
    thread_id: str
    user_input: str | None = None  # Optional user response for HITL


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
        raise HTTPException(status_code=500, detail="Graph or Checkpointer not initialized")

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
            async for event in graph.astream(inputs, config=resume_config):
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
async def webhook_endpoint(
    req: WebhookRequest,
    bg_tasks: BackgroundTasks
):
    """
    Entry point for External Events (Local BG Task).
    """
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload)
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")

    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    set_context(thread_id=tid)

    if req.event_type == "project_switched":
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            from app.domain.project.service import project_context_manager
            project_context_manager.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed
            import os

            from app.domain.codebase.indexing.manager import indexing_manager
            repo_name = os.path.basename(new_path)
            from app.domain.codebase.indexing.service import IndexingService
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
