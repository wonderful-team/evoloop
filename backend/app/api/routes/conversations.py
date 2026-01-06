from typing import List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, RemoveMessage

from app.logging import logger
from app.infrastructure.database.sql.database import get_db_session
from app.infrastructure.database.sql.models import Conversation, Message
from app.core.persistence import get_db_pool
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor

router = APIRouter()

# --- Schemas ---

class SearchResult(BaseModel):
    thread_id: str
    role: str
    content: str
    created_at: str
    match_snippet: Optional[str] = None

class RenameRequest(BaseModel):
    title: str

class ConversationListItem(BaseModel):
    thread_id: str
    title: str
    project_id: Optional[int]
    updated_at: Optional[datetime]
    status: str = "idle"

class MessageItem(BaseModel):
    id: str
    type: str
    content: str
    thinking: Optional[str]
    created_at: Optional[str]
    tasks_snapshot: Optional[List[dict]] = None  # Phase 6: Historical task steps
    
class RewindResponse(BaseModel):
    status: str
    removed_count: int = 0
    thread_id: str

# --- Endpoints ---

@router.get("/", response_model=List[ConversationListItem])
async def list_conversations(project_id: Optional[int] = None):
    """
    List conversations, optionally filtered by project_id.
    Includes real-time status from ActivityMonitor.
    """
    async with get_db_session() as session:
        stmt = select(Conversation)
        if project_id:
            stmt = stmt.where(Conversation.project_id == project_id)
            
        stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.created_at.desc()).limit(50)
        result = await session.execute(stmt)
        threads = result.scalars().all()
        
    # Inject Status
    if not threads:
        return []
        
    thread_ids = [str(t.id) for t in threads]
    status_map = await activity_monitor.get_statuses(thread_ids)

    return [
        ConversationListItem(
            thread_id=t.id, 
            title=t.title,
            project_id=t.project_id,
            updated_at=t.updated_at,
            status=status_map.get(str(t.id), "idle")
        )
        for t in threads
    ]

@router.get("/{thread_id}/messages", response_model=List[MessageItem])
async def get_conversation_messages(thread_id: str):
    """
    Get message history for a thread from the persistent SQL log.
    Includes tasks_snapshot for historical task visualization.
    """
    try:
        async with get_db_session() as session:
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.id.asc())
            result = await session.execute(stmt)
            db_messages = result.scalars().all()
            
            return [
                MessageItem(
                    id=str(m.id),
                    type=m.role,
                    content=m.content,
                    thinking=m.thinking,
                    created_at=m.created_at.isoformat() if m.created_at else None,
                    tasks_snapshot=m.tasks_snapshot  # Phase 6: Include historical tasks
                )
                for m in db_messages
            ]
            
    except Exception as e:
        logger.error(f"Failed to fetch history for {thread_id}: {e}")
        return []

@router.get("/search", response_model=List[SearchResult])
async def search_conversations(q: str, project_id: Optional[int] = None):
    """
    Full-text search on message logs.
    """
    if not q or len(q.strip()) < 2:
        return []
        
    async with get_db_session() as session:
        stmt = select(Message).where(Message.content.ilike(f"%{q}%"))
        
        if project_id:
            stmt = stmt.where(Message.project_id == project_id)
            
        stmt = stmt.order_by(Message.created_at.desc()).limit(20)
        
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        return [
            SearchResult(
                thread_id=log.thread_id,
                role=log.role,
                content=log.content, 
                created_at=str(log.created_at),
                match_snippet=log.content[:200] 
            )
            for log in logs
        ]

@router.patch("/{thread_id}")
async def rename_conversation(thread_id: str, req: RenameRequest):
    """
    Rename a conversation.
    """
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")
            
        conversation.title = req.title
        await session.commit()
        
    return {"status": "updated", "thread_id": thread_id, "title": req.title}

@router.get("/{thread_id}/activity")
async def get_thread_activity(thread_id: str):
    """Get real-time activity/status for a thread run."""
    return await activity_monitor.get_activity(thread_id)

@router.delete("/{thread_id}")
async def delete_conversation(thread_id: str):
    """Delete a conversation history and its checkpoints."""
    db_pool = get_db_pool()
    if not db_pool:
        raise HTTPException(503, "Database not initialized")
        
    try:
        # 1. Delete Checkpoints (Binary)
        async with db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoints_writes WHERE thread_id = %s", (thread_id,))
        
        # 2. Delete Thread Metadata & Logs
        async with get_db_session() as session:
            # Delete Conversation
            conversation = await session.get(Conversation, thread_id)
            if conversation:
                await session.delete(conversation)
            
            # Delete Logs (Bulk delete)
            await session.execute(delete(Message).where(Message.thread_id == thread_id))
            await session.commit()
            
        return {"status": "deleted", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        raise HTTPException(500, str(e))

@router.post("/{thread_id}/rewind", response_model=RewindResponse)
async def rewind_conversation(thread_id: str):
    """
    Rewind the conversation to the previous state (Undo last step).
    """
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
            break
            
    if not to_delete:
        return {"status": "no_human_message_found", "thread_id": thread_id, "removed_count": 0}
        
    updates = []
    for m in to_delete:
        if hasattr(m, "id") and m.id:
            updates.append(RemoveMessage(id=m.id))
            
    if updates:
        # 1. Update Graph State
        await graph.aupdate_state(config, {"messages": updates})
        
        # 2. Sync DB
        msg_ids = [u.id for u in updates]
        if msg_ids:
            try:
                async with get_db_session() as session:
                    await session.execute(delete(Message).where(Message.id.in_(msg_ids)))
                    await session.commit()
                logger.info(f"DB Sync: Deleted {len(msg_ids)} messages.")
            except Exception as e:
                logger.error(f"DB Sync Failed during rewind: {e}")
                
        return {"status": "rewound", "removed_count": len(updates), "thread_id": thread_id}
    else:
        return {"status": "failed_no_ids", "thread_id": thread_id, "removed_count": 0}
