"""
Todo Service - Business logic layer for Todo domain.

The Service layer orchestrates domain operations, applying business rules
and coordinating between the repository and external services.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import make_transient

from app.domain.todo.formatting import format_todo_list
from app.domain.todo.repository import TodoRepository, TodoRepositorySync
from app.domain.todo.schemas import (
    TodoCreate,
    TodoCreateInternal,
    TodoFilter,
    TodoListResponse,
    TodoResponse,
    TodoUpdate,
)
from app.domain.todo.utils import parse_due_date
from app.i18n.service import i18n
from app.models.todo import TodoItem, TodoPriority, TodoStatus

logger = logging.getLogger(__name__)


class TodoServiceError(Exception):
    """Base exception for Todo service errors."""

    pass


class TodoNotFoundError(TodoServiceError):
    """Raised when a Todo is not found."""

    pass


class TodoValidationError(TodoServiceError):
    """Raised when Todo data is invalid."""

    pass


class TodoService:
    """
    Service for Todo domain operations.

    This class encapsulates all business logic for todo management,
    providing a clean interface for both API and Tool layers.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TodoRepository(session)

    async def _publish_updated(self, action: str, todo_id: str | None = None, project_id: int | None = None) -> None:
        """Publish a public todo updated event (bridged to frontend SSE)."""
        try:
            from app.domain.todo.event.publishers import publish_todo_updated
            await publish_todo_updated(todo_id=todo_id, action=action, project_id=project_id)
        except Exception as e:
            logger.warning(f"[TodoService] Failed to publish todo updated event: {e}", exc_info=True)

    # ============== Creation ==============

    async def create(
        self,
        data: TodoCreate,
        source_conversation_id: str | None = None,
        source_message_id: str | None = None,
        run_id: str | None = None,
    ) -> TodoResponse:
        """
        Create a new Todo.

        Args:
            data: Todo creation data
            source_conversation_id: Optional conversation tracking ID
            source_message_id: Optional message tracking ID

        Returns:
            Created Todo as response schema

        Raises:
            TodoValidationError: If data is invalid
        """
        if not data.title or not data.title.strip():
            raise TodoValidationError(i18n.get("domain_tools.manage_todo.error_title"))

        # Parse due date if provided as string
        parsed_due_date = parse_due_date(data.due_date)
        if data.due_date and isinstance(data.due_date, str) and parsed_due_date is None:
            raise TodoValidationError(
                i18n.get("domain_tools.manage_todo.error_due_date", date=data.due_date)
            )

        # Normalize priority
        if isinstance(data.priority, str):
            priority = TodoPriority(data.priority.lower())
        else:
            priority = data.priority

        # Build internal creation data
        internal_data = TodoCreateInternal(
            title=data.title.strip(),
            description=data.description,
            priority=priority,
            category=data.category,
            due_date=parsed_due_date,
            project_id=data.project_id,
            source_conversation_id=source_conversation_id or data.source_conversation_id,
            source_message_id=source_message_id or data.source_message_id,
            run_id=run_id or data.run_id,
        )

        todo = await self.repository.create(internal_data)
        logger.info(f"Created Todo: {todo.id} - {todo.title}")
        await self._publish_updated("created", todo_id=str(todo.id), project_id=todo.project_id)
        return TodoResponse.model_validate(todo)

    # ============== Retrieval ==============

    async def get_by_id(self, todo_id: str) -> TodoResponse:
        """
        Get a Todo by ID.

        Args:
            todo_id: The todo's UUID

        Returns:
            Todo as response schema

        Raises:
            TodoNotFoundError: If todo not found
        """
        todo = await self.repository.get_by_id(todo_id)
        if not todo:
            raise TodoNotFoundError(
                i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
            )
        return TodoResponse.model_validate(todo)

    async def list_todos(
        self,
        filters: TodoFilter | None = None,
        include_total: bool = False,
    ) -> list[TodoResponse] | TodoListResponse:
        """
        List todos with optional filtering.

        Args:
            filters: Filter criteria
            include_total: Whether to include total count

        Returns:
            List of todos or paginated response with total
        """
        filters = filters or TodoFilter()
        todos = await self.repository.list_todos(filters)

        responses = [TodoResponse.model_validate(t) for t in todos]

        if include_total:
            total = await self.repository.count_todos(filters)
            return TodoListResponse(
                items=responses,
                total=total,
                limit=filters.limit,
                offset=filters.offset,
            )
        return responses

    async def list_pending_by_project(self, project_id: int, limit: int = 50) -> list[TodoResponse]:
        """
        Get pending todos for a project.

        Args:
            project_id: Project ID
            limit: Maximum results

        Returns:
            List of pending todos
        """
        filters = TodoFilter(
            project_id=project_id,
            status=TodoStatus.PENDING,
            limit=limit,
        )
        todos = await self.repository.list_todos(filters)
        return [TodoResponse.model_validate(t) for t in todos]

    # ============== Update ==============

    async def update(self, todo_id: str, data: TodoUpdate) -> TodoResponse:
        """
        Update an existing Todo.

        Args:
            todo_id: The todo's UUID
            data: Update data

        Returns:
            Updated Todo as response schema

        Raises:
            TodoNotFoundError: If todo not found
            TodoValidationError: If data is invalid
        """
        todo = await self.repository.get_by_id(todo_id)
        if not todo:
            raise TodoNotFoundError(
                i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
            )

        # Validate due date if provided
        if data.due_date and isinstance(data.due_date, str):
            parsed = parse_due_date(data.due_date)
            if parsed is None:
                raise TodoValidationError(i18n.get("domain_tools.manage_todo.error_due_date", date=data.due_date))

        # Normalize priority if provided
        if data.priority and isinstance(data.priority, str):
            data.priority = TodoPriority(data.priority.lower())

        updated = await self.repository.update(todo, data)
        logger.info(f"Updated Todo: {updated.id}")
        await self._publish_updated("updated", todo_id=str(updated.id), project_id=updated.project_id)
        return TodoResponse.model_validate(updated)

    async def mark_completed(self, todo_id: str) -> TodoResponse:
        """
        Mark a Todo as completed.

        Args:
            todo_id: The todo's UUID

        Returns:
            Updated Todo as response schema
        """
        todo = await self.repository.get_by_id(todo_id)
        if not todo:
            raise TodoNotFoundError(
                i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
            )
        updated = await self.repository.mark_status(todo, TodoStatus.COMPLETED)
        await self._publish_updated("completed", todo_id=str(updated.id), project_id=updated.project_id)
        return TodoResponse.model_validate(updated)

    async def mark_cancelled(self, todo_id: str) -> TodoResponse:
        """
        Mark a Todo as cancelled.

        Args:
            todo_id: The todo's UUID

        Returns:
            Updated Todo as response schema
        """
        todo = await self.repository.get_by_id(todo_id)
        if not todo:
            raise TodoNotFoundError(
                i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
            )
        updated = await self.repository.mark_status(todo, TodoStatus.CANCELLED)
        await self._publish_updated("updated", todo_id=str(updated.id), project_id=updated.project_id)
        return TodoResponse.model_validate(updated)

    # ============== Deletion ==============

    async def delete(self, todo_id: str) -> None:
        """
        Delete a Todo.

        Args:
            todo_id: The todo's UUID

        Raises:
            TodoNotFoundError: If todo not found
        """
        todo = await self.repository.get_by_id(todo_id)
        if not todo:
            raise TodoNotFoundError(
                i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
            )
        await self.repository.delete(todo)
        logger.info(f"Deleted Todo: {todo_id}")
        await self._publish_updated("deleted", todo_id=todo_id)

    # ============== Cleanup Operations ==============

    async def cleanup_by_message_ids(self, message_ids: list[str]) -> int:
        """
        Delete todos associated with message IDs.

        Used by cleanup engine.

        Args:
            message_ids: List of message IDs to cleanup

        Returns:
            Number of deleted todos
        """
        count = await self.repository.delete_by_message_ids(message_ids)
        logger.info(f"Cleaned up {count} todos for {len(message_ids)} messages")
        return count


class TodoServiceSync:
    """
    Synchronous version of TodoService for use in sync contexts (Tools).

    Provides the same interface but uses sync repository methods.
    """

    def __init__(self):
        self.repository = TodoRepositorySync()

    def create(
        self,
        data: TodoCreate,
        source_conversation_id: str | None = None,
        source_message_id: str | None = None,
        run_id: str | None = None,
    ) -> TodoItem:
        """Create a new Todo (sync version)."""
        if not data.title or not data.title.strip():
            raise TodoValidationError(i18n.get("domain_tools.manage_todo.error_title"))

        parsed_due_date = parse_due_date(data.due_date)

        if isinstance(data.priority, str):
            priority = TodoPriority(data.priority.lower())
        else:
            priority = data.priority

        internal_data = TodoCreateInternal(
            title=data.title.strip(),
            description=data.description,
            priority=priority,
            category=data.category,
            due_date=parsed_due_date,
            project_id=data.project_id,
            source_conversation_id=source_conversation_id or data.source_conversation_id,
            source_message_id=source_message_id or data.source_message_id,
            run_id=run_id or data.run_id,
        )

        return self.repository.create_sync(internal_data)

    def get_by_id(self, todo_id: str) -> TodoItem | None:
        """Get a Todo by ID (sync version)."""
        return self.repository.get_by_id_sync(todo_id)

    def list_todos(self, filters: TodoFilter | None = None) -> Sequence[TodoItem]:
        """List todos (sync version)."""
        return self.repository.list_todos_sync(filters)

    def mark_completed(self, todo_id: str) -> TodoItem:
        """
        Mark a Todo as completed (sync version).

        Args:
            todo_id: The todo's UUID

        Returns:
            Updated TodoItem

        Raises:
            TodoNotFoundError: If todo not found
        """
        from app.infrastructure.database import sync_session_scope

        with sync_session_scope() as session:
            # Re-query within session context
            result = session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()

            if not todo:
                raise TodoNotFoundError(
                    i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
                )

            todo.status = TodoStatus.COMPLETED
            session.commit()
            session.refresh(todo)

            # Detach for return
            make_transient(todo)
            return todo

    def mark_cancelled(self, todo_id: str) -> TodoItem:
        """
        Mark a Todo as cancelled (sync version).

        Args:
            todo_id: The todo's UUID

        Returns:
            Updated TodoItem

        Raises:
            TodoNotFoundError: If todo not found
        """
        from app.infrastructure.database import sync_session_scope

        with sync_session_scope() as session:
            result = session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()

            if not todo:
                raise TodoNotFoundError(
                    i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)
                )

            todo.status = TodoStatus.CANCELLED
            session.commit()
            session.refresh(todo)

            make_transient(todo)
            return todo

    def format_todo_list(self, todos: Sequence[TodoItem], title: str = "Todo List") -> str:
        """
        Format a list of todos for display.

        Args:
            todos: List of TodoItem instances
            title: Title for the list

        Returns:
            Rendered todo list and metadata dict.
        """
        if not todos:
            return i18n.get("domain_tools.manage_todo.no_todos")
        return format_todo_list(todos, title=title)


# ============== Factory Functions ==============


def get_todo_service(session: AsyncSession) -> TodoService:
    """Factory function to create TodoService with session."""
    return TodoService(session)


def get_todo_service_sync() -> TodoServiceSync:
    """Factory function to create sync TodoService."""
    return TodoServiceSync()
