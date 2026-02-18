import re
from datetime import datetime, timedelta
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from sqlalchemy import desc, select

from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import (
    TodoItem,
    TodoPriority,
    TodoStatus,
)
from app.utils.time import utcnow


@evoloop_tool
async def manage_todo(
    action: Literal["add", "list", "update", "delete"],
    title: str | None = None,
    description: str | None = None,
    priority: Literal["low", "medium", "high"] = "medium",
    category: str | None = None,
    due_date: str | None = None,
    # For list/update/delete
    status: Literal["pending", "completed", "cancelled"] | None = None,
    todo_id: str | None = None,
    project_id: int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Manage user Todo/Reminders items.

    **WHEN TO USE**:
    - When the user says "Remind me to..." or "Reminder for..." -> Create a todo with the specified due date.
    - PROACTIVELY verify/create todos when the user mentions future tasks (e.g., "check logs later").
    - **CRITICAL**: When executing LONG-RUNNING tasks (e.g., "running full test suite", "deploying to prod", "waiting for build"),
      you MUST PROACTIVELY suggest or create a Todo with a reasonable `due_date` (e.g., "1 hour from now") so the user knows to check back.
      Example: "I am running the tests. I added a Todo to remind you to check the results in 30 minutes."

    Args:
        action: 'add', 'list', 'update', 'delete'.
        title: Title of the todo (required for 'add').
        description: Detailed description (optional).
        priority: 'low', 'medium', 'high'.
        due_date: ISO format datetime string (e.g., "2023-12-31T23:59:00") OR relative time string (e.g. "1 hour", "30 mins", "tomorrow").
        status: For 'list' filtering or 'update' new status.
        todo_id: UUID of the todo (required for 'update', 'delete').
        project_id: Optional Project ID to associate with or filter by.
    """

    async with session_scope() as session:
        if action == "add":
            if not title:
                return i18n.get("prompts.domain_tools.manage_todo.error_title")

            # Parse relative time logic
            parsed_due_date = None
            if due_date:
                raw_lower = due_date.lower().strip()
                try:
                    # 1. Try ISO format first
                    parsed_due_date = datetime.fromisoformat(due_date)
                except ValueError:
                    # 2. Check for "None/TBD" keywords (No date)
                    if raw_lower in ["待定", "tbd", "none", "null", "pending", "unset"]:
                        parsed_due_date = None
                    else:
                        # 3. Multilingual relative parsing
                        now = utcnow()
                        
                        # Hours: (n) hours | (n) hour | (n) hrs | (n) 小时
                        h_match = re.search(r"(\d+)\s*(hour|hours|hr|hrs|小时)", raw_lower)
                        # Mins: (n) mins | (n) minutes | (n) min | (n) 分钟 | (n) 分
                        m_match = re.search(r"(\d+)\s*(min|mins|minute|minutes|分钟|分)", raw_lower)
                        # Days: (n) days | (n) day | (n) 天
                        d_match = re.search(r"(\d+)\s*(day|days|天)", raw_lower)
                        # Weeks: (n) weeks | (n) week | (n) 周 | (n) 星期
                        w_match = re.search(r"(\d+)\s*(week|weeks|周|星期)", raw_lower)
                        # Tomorrow: tomorrow | 明天
                        t_match = re.search(r"(tomorrow|明天)", raw_lower)
                        
                        if h_match:
                            parsed_due_date = now + timedelta(hours=int(h_match.group(1)))
                        elif m_match:
                            parsed_due_date = now + timedelta(minutes=int(m_match.group(1)))
                        elif d_match:
                            parsed_due_date = now + timedelta(days=int(d_match.group(1)))
                        elif w_match:
                            parsed_due_date = now + timedelta(weeks=int(w_match.group(1)))
                        elif t_match:
                            parsed_due_date = now + timedelta(days=1)
                        
                        if not parsed_due_date:
                            return i18n.get("prompts.domain_tools.manage_todo.error_due_date", date=due_date)

            todo = TodoItem(
                title=title,
                description=description,
                priority=TodoPriority(priority),
                category=category,
                due_date=parsed_due_date,
                # Try to extract thread_id from config usually
                source_conversation_id=config.get("configurable", {}).get("thread_id") if config else None,
                # Placeholder for message_id if available in config metadata
                source_message_id=config.get("metadata", {}).get("message_id") if config else None,
                project_id=project_id
            )
            session.add(todo)
            await session.commit()
            return i18n.get(
                "prompts.domain_tools.manage_todo.success_add",
                priority=todo.priority.value.upper(),
                title=todo.title,
                id=todo.id,
            )

        elif action == "list":
            query = select(TodoItem).order_by(desc(TodoItem.created_at))
            if status:
                query = query.where(TodoItem.status == TodoStatus(status))
            if project_id:
                query = query.where(TodoItem.project_id == project_id)

            result = await session.execute(query)
            todos = result.scalars().all()

            if not todos:
                return i18n.get("prompts.domain_tools.manage_todo.no_todos")

            return "\n".join([f"- [{t.status.value}] {t.title} (ID: {t.id}, Due: {t.due_date})" for t in todos])

        elif action == "update":
            if not todo_id:
                return i18n.get("prompts.domain_tools.manage_todo.error_id", action="update")

            result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()
            if not todo:
                return i18n.get("prompts.domain_tools.manage_todo.error_not_found", id=todo_id)

            if status:
                todo.status = TodoStatus(status)
            if title:
                todo.title = title
            if description:
                todo.description = description
            if category:
                todo.category = category
            if due_date:
                # (Reuse parsing logic if robust, for now keeping simple for update)
                try:
                    todo.due_date = datetime.fromisoformat(due_date)
                except Exception:
                    pass

            await session.commit()
            return i18n.get("prompts.domain_tools.manage_todo.success_update", id=todo_id)

        elif action == "delete":
            if not todo_id:
                return i18n.get("prompts.domain_tools.manage_todo.error_id", action="delete")
            result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()
            if not todo:
                return i18n.get("prompts.domain_tools.manage_todo.error_not_found", id=todo_id)

            await session.delete(todo)
            await session.commit()
            return i18n.get("prompts.domain_tools.manage_todo.success_delete", id=todo_id)

    return i18n.get("prompts.domain_tools.manage_todo.error_action")
