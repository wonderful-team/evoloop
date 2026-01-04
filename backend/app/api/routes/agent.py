from typing import Dict, Any, Optional, List, Annotated
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, RemoveMessage
from datetime import datetime, timezone

from app.logging import logger, set_context
from app.core.config import settings
from app.api.deps import get_db, SessionDep, CurrentUserOptional

from app.core.monitoring.activity import activity_monitor
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.models import Conversation, Message
from app.adapters import EventAdapter
from app.core.globals import get_graph
from app.infrastructure.database.sql.database import session_scope

# --- Background Worker ---
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.core.callbacks.evoloop_logger import EvoLoopCallbackHandler

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

class IndexingRequest(BaseModel):
    project_id: int


# --- Endpoints ---

@router.post("/chat")
async def chat_endpoint(
    req: ChatRequest, 
    current_user: CurrentUserOptional, # Use Optional Auth
    x_guest_id: Annotated[str | None, Header()] = None
):
    """
    Unified entry point for User Chat (Celery).
    """
    set_context(thread_id=req.thread_id, project_id=req.project_id)

    # --- Guest Access Control ---
    if not current_user:
        if not x_guest_id:
            raise HTTPException(status_code=401, detail="Authentication required (or X-Guest-ID)")
        
        # Check Guest Limits via Redis
        import redis.asyncio as redis
        from app.infrastructure.external.imagicbox import imagicbox_client
        
        try:
            redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            
            # 1. Get Global Config
            # TODO: Cache this config in Redis for 5-10 mins to avoid spamming member-center
            # For now, we fetch it directly or use a fallback
            try:
                # Async call to global config
                config_res = await imagicbox_client.get_ai_global_config()
                limit = 10 # Default
                if config_res and config_res.get("code") == 0:
                    limit = int(config_res.get("data", {}).get("guest_daily_limit", 10))
            except Exception as e:
                logger.warning(f"Failed to fetch guest config, using default: {e}")
                limit = 10
            
            if limit <= 0:
                raise HTTPException(status_code=403, detail="Guest chat disabled")

            # 2. Check Daily Usage
            today = datetime.now().strftime("%Y-%m-%d")
            key = f"guest:usage:{today}:{x_guest_id}"
            
            async with redis_client:
                current_usage = await redis_client.incr(key)
                if current_usage == 1:
                    await redis_client.expire(key, 86400) # 24h
            
            if current_usage > limit:
                raise HTTPException(
                    status_code=402, 
                    detail=f"Guest limit reached ({limit}/day). Please upgrade."
                )
                
            logger.info(f"Guest {x_guest_id} usage: {current_usage}/{limit}")

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Redis error during guest check: {e}")
            # Fail-Close: If Redis is down, we cannot verify quota, so we must deny to prevent abuse.
            raise HTTPException(status_code=503, detail="Guest validation service temporary unavailable.")

    # 1. Construct input state
    # SERIALIZATION: Convert HumanMessage/BaseModel to dicts for Celery
    messages = [{"type": "human", "content": req.message}] # Simple serialization
    
    inputs = {
        "messages": messages, 
        "project_id": req.project_id,
        "checkpoint_id": req.checkpoint_id
    }
    
    # Enable monitor
    goal = req.message[:50] + "..." if len(req.message) > 50 else req.message
    # Note: run_agent_background calls start_run again, but chat_endpoint does it for immediate UI feedback.
    # We should await it.
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
            
            # Log User Message
            user_msg = Message(
                thread_id=req.thread_id,
                project_id=req.project_id,
                role="human",
                content=req.message,
                thinking=None
            )
            session.add(user_msg)
            await session.flush() # Ensure FK consistency
            logger.info(f"Persisted user message for thread {req.thread_id}")
            
    except Exception as e:
        logger.error(f"Failed to upsert logic: {e}")
        # If persistence fails, the message won't be in history, but we proceed to run.
        # This explains why user sees "agent working" but no user message in history.
        # We should NOT propagate error to block chat, but log strictly.
        pass
            
    # 2. Add to Celery Task
    from app.core.workflows.tasks import run_agent_task
    run_agent_task.delay(req.thread_id, inputs)
            
    return {"status": "queued", "thread_id": req.thread_id}

@router.post("/chat/stop")
async def stop_chat(req: ChatRequest):
    """
    Stop the current generation for a thread.
    """
    await activity_monitor.stop_run(req.thread_id)
    return {"status": "stopping", "thread_id": req.thread_id}

@router.post("/chat/rewind")
async def rewind_chat(req: ChatRequest):
    """
    Rewind the conversation to the previous state (Undo last step).
    Removes the last User message and any subsequent AI messages.
    """
    thread_id = req.thread_id
    graph = get_graph()
    
    if not graph:
        raise HTTPException(503, "Graph unavailable")
        
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    
    if not state.values:
        return {"status": "empty", "thread_id": thread_id}
        
    messages = state.values.get("messages", [])
    if not messages:
        return {"status": "empty", "thread_id": thread_id}
        
    # Find the last HumanMessage
    to_delete = []
    
    # Iterate backwards
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        to_delete.append(msg)
        if isinstance(msg, HumanMessage):
            # Found the last human message.
            # We delete this AND everything that came after it (which we already collected).
            break
            
    if not to_delete:
        return {"status": "no_human_message_found", "thread_id": thread_id}
        
    # Create deletion updates
    # Ensure messages have IDs. If not, we can't delete them safely with RemoveMessage.
    # Note: add_messages reducer assigns IDs.
    updates = []
    for m in to_delete:
        if hasattr(m, "id") and m.id:
            updates.append(RemoveMessage(id=m.id))
            
    if updates:
        # 1. Update Graph State
        await graph.aupdate_state(config, {"messages": updates})
        
        # 2. Sync DB (Delete from Message table)
        # We need the IDs. 'updates' contains RemoveMessage(id=...)
        msg_ids = [u.id for u in updates]
        if msg_ids:
            try:
                from sqlalchemy import delete
                from app.infrastructure.database.sql.models import Message
                async with session_scope() as session:
                    # Execute delete
                    await session.execute(delete(Message).where(Message.id.in_(msg_ids)))
                    # Commit handled by scope
                logger.info(f"DB Sync: Deleted {len(msg_ids)} messages from history.")
            except Exception as e:
                logger.error(f"DB Sync Failed during rewind: {e}")
                
        logger.info(f"Rewound {len(updates)} messages for {thread_id}")
        return {"status": "rewound", "removed_count": len(updates)}
    else:
        logger.warning(f"No messages with IDs found to delete for {thread_id}")
        return {"status": "failed_no_ids", "thread_id": thread_id}

@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest):
    """
    Entry point for External Events (Celery).
    """
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload)
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")
        
    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    set_context(thread_id=tid)
    
    if req.event_type == "project_switched":
        # Keep inline for speed/simplicity or move to task?
        # File/Repo logic is async.
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            project_context_manager.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed
            from app.domain.codebase.indexing.manager import indexing_manager
            import os
            repo_name = os.path.basename(new_path)
            # get_or_create_repo is async, need service
            from app.domain.codebase.indexing.service import IndexingService
            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            # indexing_manager.start_watching is async.
            await indexing_manager.start_watching(new_path, repo.id)
            return {"status": "switched", "thread_id": tid, "path": new_path}

    # Serialization for Webhook messages (LangChain objects)
    serialized_msgs = []
    for m in messages:
         if isinstance(m, HumanMessage):
             serialized_msgs.append({"type": "human", "content": m.content})
         # Add support for other types if EventAdapter produces them
         else:
             serialized_msgs.append({"type": "human", "content": str(m.content)})

    inputs = {"messages": serialized_msgs}
    
    from app.core.workflows.tasks import run_agent_task
    run_agent_task.delay(tid, inputs)
    
    return {"status": "accepted", "thread_id": tid}
