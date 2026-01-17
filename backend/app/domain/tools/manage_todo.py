import re
from datetime import datetime, timedelta
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.todo import TodoItem, TodoStatus, TodoPriority
from app.utils.time import utcnow
from sqlalchemy import select, desc


@evoloop_tool
async def manage_todo(
        action: Literal['add', 'list', 'update', 'delete'],
        title: str | None = None,
        description: str | None = None,
        priority: Literal['low', 'medium', 'high'] = 'medium',
        category: str | None = None,
        due_date: str | None = None,
        # For list/update/delete
        status: Literal['pending', 'completed', 'cancelled'] | None = None,
        todo_id: str | None = None,
        project_id: int | None = None,
        config: Annotated[RunnableConfig, InjectedToolArg] = None
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
        if action == 'add':
            if not title:
                return "Error: 'title' is required for adding a todo."

            # Parse relative time logic
            parsed_due_date = None
            if due_date:
                try:
                    # Try ISO format first
                    parsed_due_date = datetime.fromisoformat(due_date)
                except ValueError:
                    # Simple relative parsing logic
                    now = utcnow()
                    if "hour" in due_date:
                        try:
                            hours = int(re.search(r'(\d+)\s*hour', due_date).group(1))
                            parsed_due_date = now + timedelta(hours=hours)
                        except:
                            pass
                    elif "min" in due_date:
                        try:
                            mins = int(re.search(r'(\d+)\s*min', due_date).group(1))
                            parsed_due_date = now + timedelta(minutes=mins)
                        except:
                            pass
                    elif "tomorrow" in due_date:
                        parsed_due_date = now + timedelta(days=1)

                    if not parsed_due_date:
                        return f"Error: Could not parse due_date '{due_date}'. Please use ISO format or simple 'X hours/mins'."

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
            return f"Todo created: [{todo.priority.value.upper()}] {todo.title} (ID: {todo.id})"

        elif action == 'list':
            query = select(TodoItem).order_by(desc(TodoItem.created_at))
            if status:
                query = query.where(TodoItem.status == TodoStatus(status))
            if project_id:
                query = query.where(TodoItem.project_id == project_id)

            result = await session.execute(query)
            todos = result.scalars().all()

            if not todos:
                return "No todos found."

            return "\n".join([f"- [{t.status.value}] {t.title} (ID: {t.id}, Due: {t.due_date})" for t in todos])

        elif action == 'update':
            if not todo_id:
                return "Error: 'todo_id' is required for update."

            result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()
            if not todo:
                return f"Error: Todo {todo_id} not found."

            if status: todo.status = TodoStatus(status)
            if title: todo.title = title
            if description: todo.description = description
            if category: todo.category = category
            if due_date:
                # (Reuse parsing logic if robust, for now keeping simple for update)
                try:
                    todo.due_date = datetime.fromisoformat(due_date)
                except:
                    pass

            await session.commit()
            return f"Todo {todo_id} updated."

        elif action == 'delete':
            if not todo_id:
                return "Error: 'todo_id' is required for delete."
            result = await session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()
            if not todo:
                return f"Error: Todo {todo_id} not found."

            await session.delete(todo)
            await session.commit()
            return f"Todo {todo_id} deleted."

    return "Error: Unknown action."
