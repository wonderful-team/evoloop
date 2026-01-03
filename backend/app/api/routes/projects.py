from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Any
import os

from app.logging import logger
from app.core.config import settings
from app.domain.project.service import project_context_manager
from app.domain.codebase.indexing.manager import indexing_manager
from app.core.globals import get_graph
from app.core.persistence import get_db_pool
from app.infrastructure.database.sql.models import Conversation, Message
from app.infrastructure.database.sql.database import get_db_session
from sqlalchemy import select, delete

router = APIRouter()

class CreateProjectRequest(BaseModel):
    name: str

class IndexingRequest(BaseModel):
    project_id: int

@router.get("/")
async def list_projects():
    """List all available projects in the configured root directory."""
    projects = await project_context_manager.scan_projects()
    
    # Inject Indexing Status
    for p in projects:
        # Assuming project dict has 'id' (it might be numeric or just name)
        # scan_projects returns dicts. Let's assume there is logic to get ID or resolve it.
        # Actually scan_projects returns Name/Path. If it doesn't return ID, we can't map status easily unless we map name -> ID or use Name as key.
        # IndexingManager uses ID (int). 
        # But wait, scan_projects fetches from FileSystem/ImagicBox. 
        # Let's see if we can get IDs.
        # For now, let's skip if no ID. 
        # Ideally, we should fetch from DB if we want accurate ID mapping.
        pass
        
    # Better approach: We need to augment the project list with DB info anyway for IDs.
    # Currently scan_projects reads FS.
    # Let's map Project Name -> ID using DB or ImagicBox?
    # Quick hack: If we have ID in the project dict, use it.
    
    # Re-reading projects.py: create_project returns `new_proj`.
    # Let's check `project_context_manager.scan_projects()` return value.
    # It likely returns what ImagicBox returns + Local checks.
    
    # Let's modify the response to include a 'status_map' or augment individually.
    # To be safe, let's expose specific endpoint status or map by ID if available.
    
    # Actually, let's just create a new endpoint for mapped status or inject if possible.
    # Assuming `p` has `id`.
    
    final_projects = []
    for p in projects:
        if "id" in p:
             p["indexing_status"] = indexing_manager.get_project_status(p["id"])
        final_projects.append(p)
    
    return {"count": len(final_projects), "projects": final_projects, "root": project_context_manager.get_working_directory("default")}

@router.post("/")
async def create_project(req: CreateProjectRequest):
    """Create a new project directory and sync to Member Center."""
    root_dir = settings.PROJECTS_ROOT
    if not root_dir:
        raise HTTPException(500, "PROJECTS_ROOT not configured")
    
    project_path = os.path.join(root_dir, req.name)
    if os.path.exists(project_path):
        raise HTTPException(400, "Project already exists")
    
    try:
        os.makedirs(project_path, exist_ok=True)
        # Create skeleton .evoloop/project.json
        meta_dir = os.path.join(project_path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "project.json"), "w") as f:
            f.write(f'{{"name": "{req.name}", "description": "Created via EvoLoop V3"}}')
            
        # Sync with Member Center
        from app.infrastructure.external.imagicbox import imagicbox_client
        res = await imagicbox_client.create_project(req.name, "Created via EvoLoop V3", project_path)
        if res.get("code") != 0:
             logger.warning(f"Failed to sync project creation to Member Center: {res}")
             
        # Re-scan to get ID/Color
        projects = await project_context_manager.scan_projects()
        new_proj = next((p for p in projects if p["name"] == req.name), None)
        return new_proj or {"name": req.name}
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(500, str(e))

@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """Delete a project (Unlink from Member Center)."""
    try:
        from app.infrastructure.external.imagicbox import imagicbox_client
        res = await imagicbox_client.delete_project(project_id)
        if res.get("code") == 0:
             return {"status": "success", "id": project_id}
        else:
             raise HTTPException(500, f"Failed to delete project: {res.get('message')}")
    except Exception as e:
        logger.error(f"Failed to delete project: {e}")
        raise HTTPException(500, str(e))

@router.post("/indexing/run")
async def run_indexing_endpoint(req: IndexingRequest, background_tasks: BackgroundTasks):
    """
    Trigger full indexing for a project.
    """
    background_tasks.add_task(indexing_manager.trigger_full_index, req.project_id)
    return {"status": "queued", "project_id": req.project_id}

# --- Conversation / Thread API ---
# These are technically "Project Resources" so keeping them here fits.

@router.get("/{project_id}/conversations")
async def list_project_conversations(project_id: int):
    """
    List conversations filtered by project_id.
    """
    async with get_db_session() as session:
        stmt = select(Conversation).where(Conversation.project_id == project_id).order_by(Conversation.updated_at.desc(), Conversation.created_at.desc()).limit(50)
        result = await session.execute(stmt)
        threads = result.scalars().all()
        
    return {
        "conversations": [
            {
                "thread_id": t.id, 
                "title": t.title,
                "project_id": t.project_id,
                "updated_at": t.updated_at
            } 
            for t in threads
        ]
    }

@router.get("/conversations/{thread_id}/history")
async def get_conversation_history(thread_id: str):
    """
    Get message history for a thread from the persistent SQL log.
    The SQL log is sanitized by DatabaseCallbackHandler for user display.
    """
    try:
        async with get_db_session() as session:
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.id.asc())
            result = await session.execute(stmt)
            db_messages = result.scalars().all()
            
            # Simple list of role/content, no complex graph parsing needed anymore!
            messages = [{"type": m.role, "content": m.content, "thinking": m.thinking} for m in db_messages]
            
            return {"messages": messages}
            
    except Exception as e:
        logger.error(f"Failed to fetch history for {thread_id}: {e}")
        # Fallback to Graph if DB fails? 
        # For now, just return empty or error. 
        # If DB is down, Graph access likely fails too since checkpointer uses DB (in theory).
        return {"messages": []}

@router.get("/conversations/{thread_id}/activity")
async def get_conversation_activity(thread_id: str):
    """Get real-time activity/status for a thread run."""
    from app.core.monitoring.activity import activity_monitor
    return await activity_monitor.get_activity(thread_id)

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation history."""
    db_pool = get_db_pool()
    if not db_pool:
        raise HTTPException(503, "Database not initialized")
        
    try:
        # 1. Delete Checkpoints (Binary)
        async with db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (conversation_id,))
                await cur.execute("DELETE FROM checkpoints_writes WHERE thread_id = %s", (conversation_id,))
        
        # 2. Delete Thread Metadata & Logs
        async with get_db_session() as session:
            # Delete Conversation
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                await session.delete(conversation)
            
            # Delete Logs (Bulk delete)
            await session.execute(delete(Message).where(Message.thread_id == conversation_id))
            await session.commit()
            
        return {"status": "deleted", "conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        raise HTTPException(500, str(e))
