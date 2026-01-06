from typing import Dict, Any, Optional, List, Annotated
from fastapi import APIRouter, HTTPException, Depends, Header, BackgroundTasks
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.logging import logger, set_context
from app.api.deps import CurrentUserOptional, verify_guest_access
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.models import Conversation, Message
from app.adapters import EventAdapter
from app.infrastructure.database.sql.database import session_scope

# --- Background Worker ---
from app.core.workflows.tasks import run_agent_background 

router = APIRouter()

# --- Models ---

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    project_id: Optional[int] = 1
    checkpoint_id: Optional[str] = None

class WebhookRequest(BaseModel):
    source: str
    event_type: str
    payload: Dict[str, Any]
    thread_id: Optional[str] = None

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
    
    # 1. Construct input state
    messages = [{"type": "human", "content": req.message}] # Simple serialization
    
    inputs = {
        "messages": messages, 
        "project_id": req.project_id,
        "checkpoint_id": req.checkpoint_id
    }
    
    # Enable monitor
    goal = req.message[:50] + "..." if len(req.message) > 50 else req.message
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


class ResumeRequest(BaseModel):
    thread_id: str
    user_input: Optional[str] = None  # Optional user response for HITL


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, bg_tasks: BackgroundTasks):
    """
    Resume a paused/interrupted graph execution.
    Used after Human-in-the-Loop interrupts where user provides input.
    """
    from app.core.globals import get_graph
    from app.core.persistence import get_checkpointer
    from langchain_core.messages import HumanMessage
    
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
        from app.core.callbacks.database_logger import DatabaseCallbackHandler
        from app.core.exceptions import AgentCancelledException
        
        callback = TransparentCallbackHandler(thread_id=req.thread_id)
        
        try:
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
            from app.domain.codebase.indexing.manager import indexing_manager
            import os
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
