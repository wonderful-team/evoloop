"""
Todo Domain Schemas - Pydantic models for data transfer.

This module defines all DTOs (Data Transfer Objects) for the Todo domain,
ensuring consistent data validation across API, Tools, and Service layers.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas.requests import BaseFilter
from app.models.todo import TodoPriority, TodoStatus


# ============== Base Schemas ==============

class TodoBase(BaseModel):
    """Base Todo fields."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TodoPriority = TodoPriority.MEDIUM
    category: str | None = Field(None, max_length=50)
    due_date: datetime | None = None
    project_id: int | None = None


# ============== Create Schemas ==============

class TodoCreate(BaseModel):
    """Schema for creating a new Todo."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: Literal["low", "medium", "high"] | TodoPriority = TodoPriority.MEDIUM
    category: str | None = Field(None, max_length=50)
    due_date: datetime | str | None = None  # str for flexible parsing
    project_id: int | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None


class TodoCreateInternal(BaseModel):
    """Internal schema after parsing and validation."""
    title: str
    description: str | None = None
    priority: TodoPriority = TodoPriority.MEDIUM
    category: str | None = None
    due_date: datetime | None = None
    project_id: int | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None


# ============== Update Schemas ==============

class TodoUpdate(BaseModel):
    """Schema for updating an existing Todo."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: TodoStatus | None = None
    priority: Literal["low", "medium", "high"] | TodoPriority | None = None
    category: str | None = Field(None, max_length=50)
    due_date: datetime | str | None = None
    project_id: int | None = None


# ============== Response Schemas ==============

class TodoResponse(BaseModel):
    """Schema for Todo responses."""
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

    model_config = ConfigDict(from_attributes=True)


# ============== Filter Schemas ==============

class TodoFilter(BaseFilter):
    """Schema for filtering Todos."""
    status: TodoStatus | None = None
    statuses: list[TodoStatus] | None = None  # For multiple status filter
    project_id: int | None = None
    priority: TodoPriority | None = None
    category: str | None = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)
    order_by: Literal["created_at", "updated_at", "due_date"] = "created_at"
    order_desc: bool = True


class TodoListResponse(BaseModel):
    """Schema for paginated list response."""
    items: list[TodoResponse]
    total: int
    limit: int
    offset: int
