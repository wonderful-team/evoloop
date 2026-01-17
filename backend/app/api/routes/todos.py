from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.sql.database import get_db
from app.infrastructure.database.sql.models.todo import TodoItem, TodoStatus, TodoPriority

router = APIRouter(tags=["todos"])

# --- Pydantic Models ---

class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TodoPriority = TodoPriority.MEDIUM
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    source_conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    project_id: Optional[int] = None

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TodoStatus] = None
    priority: Optional[TodoPriority] = None
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    project_id: Optional[int] = None

class TodoResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: TodoStatus
    priority: TodoPriority
    category: Optional[str]
    due_date: Optional[datetime]
    source_conversation_id: Optional[str]
    source_message_id: Optional[str]
    project_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Routes ---

@router.post("/", response_model=TodoResponse)
async def create_todo(
    todo_in: TodoCreate,
    session: AsyncSession = Depends(get_db)
):
    todo = TodoItem(**todo_in.model_dump())
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo

@router.get("/", response_model=List[TodoResponse])
async def list_todos(
    status: Optional[TodoStatus] = None,
    project_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    query = select(TodoItem).order_by(desc(TodoItem.created_at)).limit(limit).offset(offset)
    if status:
        query = query.where(TodoItem.status == status)
    if project_id:
         query = query.where(TodoItem.project_id == project_id)
    
    result = await session.execute(query)
    todos = result.scalars().all()
    return todos

@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: str,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@router.patch("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str,
    todo_update: TodoUpdate,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    
    update_data = todo_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)
        
    await session.commit()
    await session.refresh(todo)
    return todo

@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    
    await session.delete(todo)
    await session.commit()
    return {"message": "Todo deleted successfully"}
