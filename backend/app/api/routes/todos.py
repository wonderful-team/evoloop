from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import BaseAPIResponse
from app.domain.todo.schemas import TodoCreate, TodoResponse, TodoUpdate
from app.infrastructure.database.sql.database import get_db
from app.models.todo import (
    TodoItem,
    TodoStatus,
)

router = APIRouter(tags=["todos"])


class DeleteTodoResponse(BaseAPIResponse):
    pass


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
    return DeleteTodoResponse(message="Todo deleted successfully")
