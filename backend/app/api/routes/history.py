import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, update, text
from app.infrastructure.database.sql.database import get_db_session
from app.infrastructure.database.sql.database import get_db_session
from app.infrastructure.database.sql.models import Message, Conversation
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["conversations"])

class SearchResult(BaseModel):
    thread_id: str
    role: str
    content: str
    created_at: str
    match_snippet: Optional[str] = None

class RenameRequest(BaseModel):
    title: str

@router.get("/search", response_model=List[SearchResult])
async def search_conversations(q: str, project_id: Optional[int] = None):
    """
    Full-text search on message logs.
    """
    if not q or len(q.strip()) < 2:
        return []
        
    async with get_db_session() as session:
        # Simple LIKE query for now. For production, use PG Full Text Search (tsvector).
        # We'll assume simple LIKE to start ensuring compatibility without complex migration scripts instantly.
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
                content=log.content, # Frontend should truncate
                created_at=str(log.created_at),
                match_snippet=log.content[:200] # Simplistic snippet
            )
            for log in logs
        ]

@router.patch("/{thread_id}")
async def rename_conversation(thread_id: str, req: RenameRequest):
    """
    Rename a conversation (update title metadata).
    """
    from app.infrastructure.database.sql.models import Conversation
    
    async with get_db_session() as session:
        conversation = await session.get(Conversation, thread_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")
            
        conversation.title = req.title
        await session.commit()
        
    return {"status": "updated", "thread_id": thread_id, "title": req.title}
