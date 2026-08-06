"""
Todo Repository - Data access layer for Todo domain.

Implements the Repository Pattern to abstract database operations,
allowing the service layer to remain database-agnostic.
"""

from collections.abc import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.todo.schemas import TodoCreateInternal, TodoFilter, TodoUpdate
from app.models.todo import TodoItem, TodoStatus


class TodoRepository:
    """
    Repository for TodoItem database operations.

    All database queries are encapsulated here to keep the service layer
    clean and testable.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: TodoCreateInternal) -> TodoItem:
        """
        Create a new Todo item.

        Args:
            data: Validated todo creation data

        Returns:
            Created TodoItem instance
        """
        todo = TodoItem(**{f: getattr(data, f) for f in data.model_fields_set})
        self.session.add(todo)
        await self.session.commit()
        await self.session.refresh(todo)
        return todo

    async def get_by_id(self, todo_id: str) -> TodoItem | None:
        """
        Get a Todo by its ID.

        Args:
            todo_id: The todo's UUID

        Returns:
            TodoItem if found, None otherwise
        """
        result = await self.session.execute(
            select(TodoItem).where(TodoItem.id == todo_id)
        )
        return result.scalar_one_or_none()

    async def list_todos(self, filters: TodoFilter | None = None) -> Sequence[TodoItem]:
        """
        List todos with optional filtering.

        Args:
            filters: Filter criteria

        Returns:
            List of matching TodoItem instances
        """
        filters = filters or TodoFilter()
        query = select(TodoItem)

        # Apply filters
        if filters.status:
            query = query.where(TodoItem.status == filters.status)
        elif filters.statuses:
            query = query.where(TodoItem.status.in_(filters.statuses))

        if filters.project_id is not None:
            query = query.where(TodoItem.project_id == filters.project_id)

        if filters.priority is not None:
            query = query.where(TodoItem.priority == filters.priority)

        if filters.category is not None:
            query = query.where(TodoItem.category == filters.category)

        # Apply ordering
        order_column = getattr(TodoItem, filters.order_by, TodoItem.created_at)
        if filters.order_desc:
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(order_column)

        # Apply pagination
        query = query.limit(filters.limit).offset(filters.offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_todos(self, filters: TodoFilter | None = None) -> int:
        """
        Count todos matching the filter criteria.

        Args:
            filters: Filter criteria

        Returns:
            Total count of matching todos
        """
        filters = filters or TodoFilter()
        query = select(func.count(TodoItem.id))

        # Apply filters (same as list_todos but without pagination)
        if filters.status:
            query = query.where(TodoItem.status == filters.status)
        elif filters.statuses:
            query = query.where(TodoItem.status.in_(filters.statuses))

        if filters.project_id is not None:
            query = query.where(TodoItem.project_id == filters.project_id)

        if filters.priority is not None:
            query = query.where(TodoItem.priority == filters.priority)

        if filters.category is not None:
            query = query.where(TodoItem.category == filters.category)

        result = await self.session.execute(query)
        return result.scalar()

    async def update(self, todo: TodoItem, data: TodoUpdate) -> TodoItem:
        """
        Update an existing Todo.

        Args:
            todo: The todo instance to update
            data: Update data

        Returns:
            Updated TodoItem instance
        """
        update_data = data.model_dump(exclude_unset=True, exclude={"due_date"})

        # Handle due_date separately if it's a string
        if data.due_date is not None:
            from app.domain.todo.utils import parse_due_date

            update_data["due_date"] = parse_due_date(data.due_date)

        for key, value in update_data.items():
            setattr(todo, key, value)

        await self.session.commit()
        await self.session.refresh(todo)
        return todo

    async def delete(self, todo: TodoItem) -> None:
        """
        Delete a Todo item.

        Args:
            todo: The todo instance to delete
        """
        await self.session.delete(todo)
        await self.session.commit()

    async def mark_status(self, todo: TodoItem, status: TodoStatus) -> TodoItem:
        """
        Update a Todo's status.

        Args:
            todo: The todo instance
            status: New status

        Returns:
            Updated TodoItem instance
        """
        todo.status = status
        await self.session.commit()
        await self.session.refresh(todo)
        return todo

    async def get_by_project(
        self, 
        project_id: int, 
        statuses: list[TodoStatus] | None = None,
        limit: int = 50
    ) -> Sequence[TodoItem]:
        """
        Get todos for a specific project.

        Args:
            project_id: Project ID
            statuses: Optional list of statuses to filter
            limit: Maximum results

        Returns:
            List of matching TodoItem instances
        """
        query = select(TodoItem).where(
            TodoItem.project_id == project_id
        ).order_by(desc(TodoItem.created_at)).limit(limit)
        
        if statuses:
            query = query.where(TodoItem.status.in_(statuses))

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_message_ids(self, message_ids: list[str]) -> Sequence[TodoItem]:
        """
        Get todos associated with specific message IDs.

        Used for cleanup operations.

        Args:
            message_ids: List of message IDs

        Returns:
            List of matching TodoItem instances
        """
        result = await self.session.execute(
            select(TodoItem).where(TodoItem.source_message_id.in_(message_ids))
        )
        return result.scalars().all()

    async def delete_by_message_ids(self, message_ids: list[str]) -> int:
        """
        Delete todos associated with specific message IDs.

        Used for cleanup operations.

        Args:
            message_ids: List of message IDs

        Returns:
            Number of deleted records
        """
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(TodoItem).where(TodoItem.source_message_id.in_(message_ids))
        )
        await self.session.commit()
        return result.rowcount


# ============== Sync Repository for non-async contexts ==============


class TodoRepositorySync:
    """
    Synchronous version of TodoRepository for use in sync contexts.

    Uses session_scope for automatic session management.
    """

    def create_sync(self, data: TodoCreateInternal) -> TodoItem:
        """Create a new Todo (sync version)."""
        from app.infrastructure.database import session_scope

        with session_scope() as session:
            todo = TodoItem(**{f: getattr(data, f) for f in data.model_fields_set})
            session.add(todo)
            session.commit()
            session.refresh(todo)
            # Detach from session before returning
            from sqlalchemy.orm import make_transient

            make_transient(todo)
            return todo

    def get_by_id_sync(self, todo_id: str) -> TodoItem | None:
        """Get a Todo by ID (sync version)."""
        from app.infrastructure.database import session_scope

        with session_scope() as session:
            result = session.execute(select(TodoItem).where(TodoItem.id == todo_id))
            todo = result.scalar_one_or_none()
            if todo:
                from sqlalchemy.orm import make_transient

                make_transient(todo)
            return todo

    def list_todos_sync(self, filters: TodoFilter | None = None) -> Sequence[TodoItem]:
        """List todos with filters (sync version)."""
        from app.infrastructure.database import session_scope

        filters = filters or TodoFilter()
        with session_scope() as session:
            query = select(TodoItem)

            if filters.status:
                query = query.where(TodoItem.status == filters.status)
            elif filters.statuses:
                query = query.where(TodoItem.status.in_(filters.statuses))

            if filters.project_id is not None:
                query = query.where(TodoItem.project_id == filters.project_id)

            if filters.priority is not None:
                query = query.where(TodoItem.priority == filters.priority)

            order_column = getattr(TodoItem, filters.order_by, TodoItem.created_at)
            if filters.order_desc:
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(order_column)

            query = query.limit(filters.limit).offset(filters.offset)

            result = session.execute(query)
            todos = result.scalars().all()

            # Detach all results
            from sqlalchemy.orm import make_transient

            for todo in todos:
                make_transient(todo)

            return todos
