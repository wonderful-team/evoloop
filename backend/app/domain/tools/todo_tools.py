"""
Todo Tools - Individual tools for todo management.

This module provides standalone tools for todo operations,
replacing the monolithic manage_todo facade.
"""
import re
from datetime import datetime, timedelta
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from sqlalchemy import desc, select

from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoItem, TodoPriority, TodoStatus
from app.utils import ContentFormatter
from app.utils.time import utcnow


def _parse_due_date(due_date: str | None) -> datetime | None:
    """Parse due date from various formats."""
    if not due_date:
        return None
    
    raw_lower = due_date.lower().strip()
    
    # 1. Try ISO format first
    try:
        return datetime.fromisoformat(due_date)
    except ValueError:
        pass
    
    # 2. Check for "None/TBD" keywords (No date)
    if raw_lower in ["待定", "tbd", "none", "null", "pending", "unset"]:
        return None
    
    # 3. Multilingual relative parsing
    now = utcnow()
    
    # Hours: (n) hours | (n) hour | (n) hrs | (n) 小时
    h_match = re.search(r"(\d+)\s*(hour|hours|hr|hrs|小时)", raw_lower)
    if h_match:
        return now + timedelta(hours=int(h_match.group(1)))
    
    # Mins: (n) mins | (n) minutes | (n) min | (n) 分钟 | (n) 分
    m_match = re.search(r"(\d+)\s*(min|mins|minute|minutes|分钟|分)", raw_lower)
    if m_match:
        return now + timedelta(minutes=int(m_match.group(1)))
    
    # Days: (n) days | (n) day | (n) 天
    d_match = re.search(r"(\d+)\s*(day|days|天)", raw_lower)
    if d_match:
        return now + timedelta(days=int(d_match.group(1)))
    
    # Weeks: (n) weeks | (n) week | (n) 周 | (n) 星期
    w_match = re.search(r"(\d+)\s*(week|weeks|周|星期)", raw_lower)
    if w_match:
        return now + timedelta(weeks=int(w_match.group(1)))
    
    # Tomorrow: tomorrow | 明天
    if re.search(r"(tomorrow|明天)", raw_lower):
        return now + timedelta(days=1)
    
    return None


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.create_todo",
    name_map={"zh": "创建待办", "en": "Create Todo"}
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
    
    # Parse due date
    parsed_due_date = _parse_due_date(due_date)
    if due_date and parsed_due_date is None:
        return i18n.get("domain_tools.manage_todo.error_due_date", date=due_date)
    
    async with session_scope() as session:
        todo = TodoItem(
            title=title,
            description=description,
            priority=TodoPriority(priority),
            category=category,
            due_date=parsed_due_date,
            source_conversation_id=config.get("configurable", {}).get("thread_id") if config else None,
            source_message_id=config.get("metadata", {}).get("message_id") if config else None,
            project_id=project_id
        )
        session.add(todo)
        await session.commit()
        
        return i18n.get(
            "domain_tools.manage_todo.success_add",
            priority=todo.priority.value.upper(),
            title=todo.title,
            id=todo.id,
        )


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.list_todos",
    name_map={"zh": "列出现办", "en": "List Todos"}
)
async def list_todos(
    status: Literal["pending", "completed", "cancelled"] | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> str:
    """
    List Todo items with optional filtering.
    
    Args:
        status: Filter by status - 'pending', 'completed', or 'cancelled'.
                If not specified, shows all non-cancelled todos.
        project_id: Filter by Project ID.
        limit: Maximum number of todos to return (default 50).
    
    Examples:
        list_todos()  # List all active todos
        list_todos(status="pending")
        list_todos(project_id=123, limit=10)
    """
    async with session_scope() as session:
        query = select(TodoItem).order_by(desc(TodoItem.created_at))
        
        if status:
            query = query.where(TodoItem.status == TodoStatus(status))
        else:
            # Default: exclude cancelled
            query = query.where(TodoItem.status != TodoStatus.cancelled)
        
        if project_id:
            query = query.where(TodoItem.project_id == project_id)
        
        result = await session.execute(query.limit(limit))
        todos = result.scalars().all()
        
        if not todos:
            return i18n.get("domain_tools.manage_todo.no_todos")
        
        return ContentFormatter.todo_list(todos, title="Todo List")


# NOTE: The following actions from manage_todo are consolidated into list_todos
# with status filtering, or can be added as separate tools if needed:
# - update_todo: Can be done via list_todos to find ID, then manual update
# - delete_todo: Mark as cancelled via status update
