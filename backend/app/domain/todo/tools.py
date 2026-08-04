"""
Todo Tools - Agent-facing tools for todo management.

These tools provide the interface between the AI agent and the Todo domain.
All business logic is delegated to the TodoService layer.
"""

from typing import Annotated, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.domain.todo.formatting import format_todo_list
from app.domain.todo.schemas import TodoCreate, TodoFilter
from app.domain.todo.service import TodoNotFoundError
from app.domain.todo.utils import parse_due_date
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoStatus


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.create_todo"
)
async def create_todo(
    title: str,
    description: str | None = None,
    due_date: str | None = None,
    priority: Literal["low", "medium", "high"] = "medium",
    category: str | None = None,
    project_id: int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create a new Todo/Reminder item.

    **WHEN TO USE**:
    - When the user says "Remind me to..." or "Reminder for..."
    - PROACTIVELY create todos for future tasks (e.g., "check logs later").
    - **CRITICAL**: When executing LONG-RUNNING tasks (e.g., "running tests",
      "deploying to prod"), create a Todo with a reasonable `due_date`
      so the user knows to check back.

    Args:
        title: The todo title (required).
        description: Detailed description (optional).
        due_date: Due date in various formats:
                  - ISO format: "2023-12-31T23:59:00"
                  - Relative: "1 hour", "30 mins", "2 days", "tomorrow"
                  - Chinese: "1小时", "30分钟", "明天"
        priority: 'low', 'medium' (default), or 'high'.
        category: Optional category/tag for grouping.
        project_id: Optional Project ID to associate with.

    Examples:
        create_todo(title="Review PR #123", due_date="1 hour")
        create_todo(
            title="Check test results",
            description="Verify all tests passed in CI",
            due_date="30 mins",
            priority="high"
        )
    """
    if not title:
        return i18n.get("domain_tools.manage_todo.error_title")

    # Parse due date using domain utility (which wraps parse_relative_time)
    parsed_due_date = parse_due_date(due_date)
    if due_date and parsed_due_date is None:
        return i18n.get("domain_tools.manage_todo.error_due_date", date=due_date)

    # Extract source IDs from config
    source_conversation_id = None
    source_message_id = None
    run_id = None
    if config:
        source_conversation_id = config.get("configurable", {}).get("thread_id")
        source_message_id = config.get("metadata", {}).get("message_id")
        run_id = config.get("metadata", {}).get("run_id")

    # Create via service layer
    async with session_scope() as session:
        from app.domain.todo.service import TodoService

        service = TodoService(session)
        todo = await service.create(
            data=TodoCreate(
                title=title,
                description=description,
                due_date=due_date,  # Service will parse again
                priority=priority,
                category=category,
                project_id=project_id,
            ),
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            run_id=run_id,
        )

    return i18n.get(
        "domain_tools.manage_todo.success_add",
        priority=todo.priority.value.upper(),
        title=todo.title,
        id=todo.id,
    ), {"id": todo.id}


@evoloop_tool(summary_template="evoloop.tool_summary.list_todos")
async def list_todos(
    status: Literal["pending", "completed", "cancelled"] | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> str:
    """
    List Todo items with optional filtering.

    Use this to show users their pending todos, or to find a todo ID
    that you need to complete or cancel.

    Args:
        status: Filter by status - 'pending', 'completed', or 'cancelled'.
                If not specified, shows all non-cancelled todos.
        project_id: Filter by Project ID.
        limit: Maximum number of todos to return (default 50).

    Examples:
        list_todos()  # List all active todos
        list_todos(status="pending")  # Show only pending
        list_todos(project_id=123, limit=10)
    """
    # Build filter
    filter_status = TodoStatus(status) if status else None
    filters = TodoFilter(
        status=filter_status,
        project_id=project_id,
        limit=limit,
    )

    # Query via service layer
    async with session_scope() as session:
        from app.domain.todo.service import TodoService

        service = TodoService(session)
        todos = await service.list_todos(filters)

    if not todos:
        return i18n.get("domain_tools.manage_todo.no_todos")

    return format_todo_list(todos, title="Todo List"), {"count": len(todos)}


@evoloop_tool(
    is_state_mutating=True, summary_template="evoloop.tool_summary.complete_todo"
)
async def complete_todo(todo_id: str) -> str:
    """
    Mark a Todo as completed.

    **WHEN TO USE**:
    - When the user says "I finished..." or "Mark as done..."
    - After completing a task that was previously created as a todo
    - When the user confirms a task is complete

    Args:
        todo_id: The ID of the todo to complete (from list_todos).

    Examples:
        complete_todo(todo_id="abc-123")
        complete_todo(todo_id="550e8400-e29b-41d4-a716-446655440000")

    Note:
        If you don't know the todo_id, use list_todos() first to find it.
    """
    if not todo_id:
        return i18n.get("domain_tools.manage_todo.error_id", action="complete")

    async with session_scope() as session:
        from app.domain.todo.service import TodoService

        service = TodoService(session)
        try:
            todo = await service.mark_completed(todo_id)
            return i18n.get(
                "domain_tools.manage_todo.success_update", id=todo.id
            ) + f" [{todo.status.value}] {todo.title}", {
                "id": todo.id,
                "status": todo.status.value,
            }
        except TodoNotFoundError:
            return i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)


@evoloop_tool(
    is_state_mutating=True, summary_template="evoloop.tool_summary.cancel_todo"
)
async def cancel_todo(todo_id: str) -> str:
    """
    Mark a Todo as cancelled.

    **WHEN TO USE**:
    - When the user says "Cancel..." or "I don't need to do this anymore"
    - When a task is no longer relevant
    - When the user wants to remove a todo without completing it

    Args:
        todo_id: The ID of the todo to cancel (from list_todos).

    Examples:
        cancel_todo(todo_id="abc-123")
        cancel_todo(todo_id="550e8400-e29b-41d4-a716-446655440000")

    Note:
        If you don't know the todo_id, use list_todos() first to find it.
        Cancelled todos won't appear in normal list_todos() results.
    """
    if not todo_id:
        return i18n.get("domain_tools.manage_todo.error_id", action="cancel")

    async with session_scope() as session:
        from app.domain.todo.service import TodoService

        service = TodoService(session)
        try:
            todo = await service.mark_cancelled(todo_id)
            return i18n.get(
                "domain_tools.manage_todo.success_update",
                id=todo.id
            ) + f" [{todo.status.value}] {todo.title}", {"id": todo.id, "status": todo.status.value}
        except TodoNotFoundError:
            return i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
