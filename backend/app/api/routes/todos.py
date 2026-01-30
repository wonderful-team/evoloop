from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.sql.database import get_db
from app.models.todo import (
    TodoItem,
    TodoPriority,
    TodoStatus,
)

router = APIRouter(tags=["todos"])

# --- Pydantic Models ---


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: TodoPriority = TodoPriority.MEDIUM
    category: str | None = None
    due_date: datetime | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    project_id: int | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TodoStatus | None = None
    priority: TodoPriority | None = None
    category: str | None = None
    due_date: datetime | None = None
    project_id: int | None = None


class TodoResponse(BaseModel):
    id: str
    title: str
    description: str | None
    status: TodoStatus
    priority: TodoPriority
    category: str | None
    due_date: datetime | None
    source_conversation_id: str | None
    source_message_id: str | None
    project_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Routes ---


@router.post("/", response_model=TodoResponse)
async def create_todo(todo_in: TodoCreate, session: AsyncSession = Depends(get_db)):
    todo = TodoItem(**todo_in.model_dump())
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


@router.get("/", response_model=list[TodoResponse])
async def list_todos(
    status: TodoStatus | None = None,
    project_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
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
async def get_todo(todo_id: str, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


@router.patch("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str, todo_update: TodoUpdate, session: AsyncSession = Depends(get_db)
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
async def delete_todo(todo_id: str, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
    todo = result.scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    await session.delete(todo)
    await session.commit()
    return {"message": "Todo deleted successfully"}
