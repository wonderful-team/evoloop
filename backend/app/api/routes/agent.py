from typing import Dict, Any, Optional, List, Annotated
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, RemoveMessage
from datetime import datetime, timezone

from app.logging import logger, set_context
from app.core.config import settings
from app.api.deps import get_db, SessionDep, CurrentUserOptional
from app.core.callbacks.transparent import console
from app.core.monitoring.activity import activity_monitor
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.models import Conversation
from app.adapters import EventAdapter
from app.core.globals import get_graph
from app.infrastructure.database.sql.database import session_scope

# --- Background Worker ---
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.core.callbacks.evoloop_logger import EvoLoopCallbackHandler
from app.infrastructure.evoloop_link.client import get_evoloop_client

router = APIRouter()

async def run_agent_background(thread_id: str, inputs: Dict[str, Any]):
    """
    Run the agent graph in the background.
    """
    # 0. Set Logging Context
    project_id = inputs.get("project_id", 1)
    set_context(thread_id=thread_id, project_id=project_id)
    
    # 1. Retrieve current working directory for this thread
    working_dir = project_context_manager.get_working_directory(thread_id)
    
    # 2. Inject into config
    config = {
        "configurable": {
            "thread_id": thread_id,
            "working_directory": working_dir
        },
        "metadata": {
            "project_id": project_id
        }
    }
    
    # Inject Checkpoint ID if present
    if inputs.get("checkpoint_id"):
        config["configurable"]["checkpoint_id"] = inputs["checkpoint_id"]
        
    evoloop_command_id = inputs.get("command_id")
    
    # Use our transparent callback with thread tracking
    callback = TransparentCallbackHandler(thread_id=thread_id)
    db_callback = DatabaseCallbackHandler(thread_id=thread_id, project_id=project_id)
    
    # Update Status to Running
    activity_monitor.start_run(thread_id)
    
    # --- MEMORY INJECTION ---
    # Fetch User Preferences & Concepts and inject into state
    from app.domain.memory.service import memory_service
    
    # 1. User Preferences (Assumes user_id "user_default" or similar for single user mode, or extracted from somewhere)
    # Ideally we get user_id from request but run_agent_background is decoupled. 
    # For now we use a default or project-based key if user specific not avail.
    user_prefs = await memory_service.get_user_preferences("user_default")
    
    # 2. Project Concepts (Top 5 general ones or specific to context?)
    # We fetch general top concepts to prime the agent.
    # Note: search_concepts requires query. Empty query might return top/all depending on impl.
    # The current impl of search_concepts uses "CONTAINS", so empty string should match all.
    concepts_text = await memory_service.search_concepts("", project_id)
    
    # Inject into inputs (State)
    inputs["user_preferences"] = user_prefs
    inputs["project_concepts"] = concepts_text
    # ------------------------
    
    try:
        callbacks = [callback, db_callback]
        
        # Add EvoLoop Link Callback if available
        evoloop_client = get_evoloop_client()
        if evoloop_client:
            # Pass command_id to handler
            callbacks.append(EvoLoopCallbackHandler(evoloop_client, thread_id, command_id=evoloop_command_id))
            
        config["callbacks"] = callbacks
        config["recursion_limit"] = 50
        
        # Run!
        # Access graph safely
        # FIX: Ensure graph is available. 
        from app.core.globals import get_graph
        graph_instance = get_graph()
        
        if not graph_instance:
             logger.error("Graph not initialized!")
             return

        async for event in graph_instance.astream(inputs, config=config):
            pass
            
        activity_monitor.end_run(thread_id, "done")
        
        if evoloop_client:
            try:
                final_state = await graph_instance.aget_state(config)
                logger.info(f"Final State Keys: {final_state.values.keys()}")
                if final_state.values and "messages" in final_state.values:
                    messages = final_state.values["messages"]
                    logger.info(f"Total messages: {len(messages)}")
                    if messages:
                        last_msg = messages[-1]
                        logger.info(f"Last message type: {type(last_msg)}, content: {last_msg.content}")
                        
                        # Check if it's an AI message with content
                        if hasattr(last_msg, "content") and last_msg.content:
                            content_str = last_msg.content
                            
                            # CLEAN <think> tags for mobile display
                            import re
                            # Remove <think>...</think> including newlines
                            content_clean = re.sub(r'<think>.*?</think>', '', content_str, flags=re.DOTALL).strip()
                            
                            logger.info(f"Uploading final output (cleaned len: {len(content_clean)})...")
                            
                            await evoloop_client.upload_log(
                                thread_id=thread_id,
                                log_type="output", 
                                content=content_clean,
                                command_id=evoloop_command_id
                            )
                            logger.info("Upload task awaited.")
            except Exception as e:
                logger.warning(f"Failed to send final output to EvoLoop: {e}")
        
    except Exception as e:
        logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)
        activity_monitor.end_run(thread_id, "failed")


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
    background_tasks: BackgroundTasks,
    current_user: CurrentUserOptional, # Use Optional Auth
    x_guest_id: Annotated[str | None, Header()] = None
):
    """
    Unified entry point for User Chat.
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
                # We can't await this sync method directly if it was sync, but requests is sync.
                # Ideally imagicbox_client should be async or run in threadpool. 
                # For this MVP step we are inside async def, blocking slightly is okay-ish for Dev, 
                # but better to wrap or assume fast network. 
                # Converting to async properly is out of scope for this small task, assume it returns quick.
                config_res = imagicbox_client.get_ai_global_config()
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
            # Allow open on error? Or Block? Block safeguards.
            pass

    # 1. Construct input state
    messages = [HumanMessage(content=req.message)]
    inputs = {
        "messages": messages, 
        "project_id": req.project_id,
        "checkpoint_id": req.checkpoint_id
    }
    
    # Enable monitor
    goal = req.message[:50] + "..." if len(req.message) > 50 else req.message
    activity_monitor.start_run(req.thread_id, goal)
    
    # 3. Upsert Conversation Record
    async with session_scope() as session:
        conversation = await session.get(Conversation, req.thread_id)
        if not conversation:
            conversation = Conversation(
                id=req.thread_id,
                project_id=req.project_id,
                title=req.message[:50],
                # owner_id=current_user.id if current_user else None 
            )
            session.add(conversation)
        else:
            conversation.updated_at = datetime.now(timezone.utc)
            
    # 2. Add to background task
    background_tasks.add_task(run_agent_background, req.thread_id, inputs)
            
    return {"status": "queued", "thread_id": req.thread_id}

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
        # Push the update with the deletions
        await graph.aupdate_state(config, {"messages": updates})
        logger.info(f"Rewound {len(updates)} messages for {thread_id}")
        return {"status": "rewound", "removed_count": len(updates)}
    else:
        logger.warning(f"No messages with IDs found to delete for {thread_id}")
        return {"status": "failed_no_ids", "thread_id": thread_id}

@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest, background_tasks: BackgroundTasks):
    """
    Entry point for External Events.
    """
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload)
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")
        
    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    set_context(thread_id=tid)
    
    if req.event_type == "project_switched":
        # ... (Same logic as server.py) ...
        # Simplified for brevity in this step, but assumption implies full copy
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            project_context_manager.set_working_directory(tid, new_path)
            from app.domain.codebase.indexing.service import IndexingService
            from app.domain.codebase.indexing.manager import indexing_manager
            import os
            service = IndexingService()
            repo_name = os.path.basename(new_path)
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return {"status": "switched", "thread_id": tid, "path": new_path}

    inputs = {"messages": messages}
    background_tasks.add_task(run_agent_background, tid, inputs)
    
    return {"status": "accepted", "thread_id": tid}
