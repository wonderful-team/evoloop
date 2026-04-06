"""
Todo Domain Module

A standardized domain module for Todo management following DDD patterns:
- schemas: Data transfer objects (DTOs)
- repository: Data access layer
- service: Business logic layer
- tools: Agent-facing tools
- utils: Helper utilities

Usage:
    from app.domain.todo import TodoService, TodoCreate, TodoFilter
    
    # In async context (API)
    service = TodoService(session)
    todo = await service.create(TodoCreate(title="Review PR"))
    
    # In sync context (Tools)
    from app.domain.todo import get_todo_service_sync
    service = get_todo_service_sync()
    todo = service.create(TodoCreate(title="Review PR"))
    
    # Tools are auto-registered
    from app.domain.todo import create_todo, list_todos
"""

# Schemas
from app.domain.todo.schemas import (
    TodoBase,
    TodoCreate,
    TodoCreateInternal,
    TodoFilter,
    TodoListResponse,
    TodoResponse,
    TodoUpdate,
)

# Repository
from app.domain.todo.repository import TodoRepository, TodoRepositorySync

# Service
from app.domain.todo.service import (
    TodoService,
    TodoServiceError,
    TodoServiceSync,
    TodoNotFoundError,
    TodoValidationError,
    get_todo_service,
    get_todo_service_sync,
)

# Tools (auto-registered via @evoloop_tool decorator)
from app.domain.todo.tools import (
    cancel_todo,
    complete_todo,
    create_todo,
    list_todos,
)

# Utils
from app.domain.todo.utils import (
    format_todo_summary,
    is_overdue,
    parse_due_date,
    get_priority_weight,
    should_remind,
    get_status_transition_allowed,
)

__all__ = [
    # Schemas
    "TodoBase",
    "TodoCreate",
    "TodoCreateInternal",
    "TodoUpdate",
    "TodoResponse",
    "TodoFilter",
    "TodoListResponse",
    # Repository
    "TodoRepository",
    "TodoRepositorySync",
    # Service
    "TodoService",
    "TodoServiceSync",
    "TodoServiceError",
    "TodoNotFoundError",
    "TodoValidationError",
    "get_todo_service",
    "get_todo_service_sync",
    # Tools
    "create_todo",
    "list_todos",
    "complete_todo",
    "cancel_todo",
    # Utils
    "parse_due_date",
    "format_todo_summary",
    "is_overdue",
    "get_priority_weight",
    "should_remind",
    "get_status_transition_allowed",
]
