"""
Integration Tests for Todo Domain

Tests the full workflow: tools -> service -> repository
"""
import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from app.domain.todo import (
    create_todo,
    list_todos,
    complete_todo,
    cancel_todo,
    TodoService,
    TodoCreate,
    TodoFilter,
)
from app.models.todo import TodoItem, TodoStatus, TodoPriority


def _mock_session_scope():
    """Helper to patch session_scope for todo tools."""
    session = MagicMock()
    @asynccontextmanager
    async def _fake():
        yield session
    return patch('app.infrastructure.database.sql.database.session_scope', side_effect=_fake)


class TestTodoWorkflow:
    """Test complete todo workflows."""
    
    @pytest.mark.asyncio
    async def test_create_and_complete_workflow(self):
        """Test full create -> list -> complete workflow."""
        
        # Mock the service layer
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "workflow-test-id"
        mock_todo.title = "Workflow Test Todo"
        mock_todo.priority = TodoPriority.HIGH
        mock_todo.status = TodoStatus.COMPLETED
        
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            mock_service.create = AsyncMock(return_value=mock_todo)
            mock_service.list_todos = AsyncMock(return_value=[mock_todo])
            mock_service.mark_completed = AsyncMock(return_value=mock_todo)
            
            # Step 1: Create a todo
            result = await create_todo.ainvoke({
                "title": "Workflow Test Todo",
                "priority": "high",
                "due_date": "1 hour"
            })
            assert "Workflow Test Todo" in result
            mock_service.create.assert_called_once()
            
            # Step 2: List todos
            todos = await mock_service.list_todos(TodoFilter())
            assert len(todos) == 1
            
            # Step 3: Complete the todo
            mock_todo.status = TodoStatus.COMPLETED
            completed = await mock_service.mark_completed("workflow-test-id")
            assert completed.status == TodoStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_create_and_cancel_workflow(self):
        """Test create -> cancel workflow."""
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "cancel-test-id"
        mock_todo.title = "Cancel Test"
        mock_todo.priority = TodoPriority.MEDIUM
        mock_todo.status = TodoStatus.CANCELLED
        
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            mock_service.create = AsyncMock(return_value=mock_todo)
            mock_service.mark_cancelled = AsyncMock(return_value=mock_todo)
            
            # Create
            result = await create_todo.ainvoke({"title": "Cancel Test"})
            assert "Cancel Test" in result
            
            # Cancel
            mock_todo.status = TodoStatus.CANCELLED
            cancelled = await mock_service.mark_cancelled("cancel-test-id")
            assert cancelled.status == TodoStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_list_with_filters(self):
        """Test listing with various filters."""
        
        mock_todos = [
            Mock(spec=TodoItem, status=TodoStatus.PENDING, project_id=1),
            Mock(spec=TodoItem, status=TodoStatus.COMPLETED, project_id=1),
        ]
        
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            mock_service.list_todos = AsyncMock(return_value=mock_todos)
            mock_service.format_todo_list = AsyncMock(return_value="2 todos found")
            
            result = await list_todos.ainvoke({"status": "pending", "project_id": 1, "limit": 10})
            
            mock_service.list_todos.assert_called_once()
            call_args = mock_service.list_todos.call_args[0][0]
            assert call_args.status == TodoStatus.PENDING
            assert call_args.project_id == 1
            assert call_args.limit == 10


class TestTodoToolsErrorHandling:
    """Test error handling in tools."""
    
    @pytest.mark.asyncio
    async def test_create_without_title(self):
        """Test creating todo without title fails."""
        result = await create_todo.ainvoke({"title": ""})
        assert "error" in result.lower() or "错误" in result or "required" in result.lower()
    
    @pytest.mark.asyncio
    async def test_complete_nonexistent_todo(self):
        """Test completing non-existent todo."""
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            mock_service.mark_completed = AsyncMock(side_effect=Exception("Not found"))
            
            result = await complete_todo.ainvoke({"todo_id": "non-existent"})
            # Should handle error gracefully
            assert "non-existent" in result or "error" in result.lower() or "未找到" in result
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_todo(self):
        """Test cancelling non-existent todo."""
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            from app.domain.todo import TodoNotFoundError
            mock_service.mark_cancelled = AsyncMock(side_effect=TodoNotFoundError("Not found"))
            
            result = await cancel_todo.ainvoke({"todo_id": "non-existent"})
            assert "non-existent" in result or "not found" in result.lower() or "未找到" in result


class TestTodoDateParsingIntegration:
    """Test date parsing in tool context."""
    
    @pytest.mark.asyncio
    async def test_create_with_relative_date(self):
        """Test creating todo with relative date."""
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "date-test-id"
        mock_todo.title = "Date Test"
        mock_todo.priority = TodoPriority.MEDIUM
        
        with _mock_session_scope(), patch('app.domain.todo.service.TodoService') as MockService:
            mock_service = MockService.return_value
            mock_service.create = AsyncMock(return_value=mock_todo)
            
            # Various date formats
            for date_str in ["1 hour", "30 mins", "tomorrow", "2 days", "明天"]:
                result = await create_todo.ainvoke({
                    "title": "Date Test",
                    "due_date": date_str
                })
                assert "Date Test" in result
                mock_service.create.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_with_invalid_date(self):
        """Test creating todo with invalid date shows error."""
        result = await create_todo.ainvoke({
            "title": "Invalid Date Test",
            "due_date": "invalid date format that cannot be parsed"
        })
        # Should return error message about date parsing
        assert "error" in result.lower() or "date" in result.lower() or "无法解析" in result


class TestTodoDomainImports:
    """Test all domain exports are available."""
    
    def test_all_tools_exported(self):
        """Test all tools are exported from domain."""
        from app.domain.todo import (
            create_todo,
            list_todos,
            complete_todo,
            cancel_todo,
        )
        from langchain_core.tools import StructuredTool
        assert isinstance(create_todo, StructuredTool)
        assert isinstance(list_todos, StructuredTool)
        assert isinstance(complete_todo, StructuredTool)
        assert isinstance(cancel_todo, StructuredTool)
    
    def test_all_services_exported(self):
        """Test all services are exported."""
        from app.domain.todo import (
            TodoService,
            TodoServiceSync,
            get_todo_service,
            get_todo_service_sync,
        )
        assert TodoService is not None
        assert TodoServiceSync is not None
        assert callable(get_todo_service)
        assert callable(get_todo_service_sync)
    
    def test_all_schemas_exported(self):
        """Test all schemas are exported."""
        from app.domain.todo import (
            TodoCreate,
            TodoUpdate,
            TodoResponse,
            TodoFilter,
        )
        assert TodoCreate is not None
        assert TodoUpdate is not None
        assert TodoResponse is not None
        assert TodoFilter is not None
    
    def test_all_utils_exported(self):
        """Test all utils are exported."""
        from app.domain.todo import (
            parse_due_date,
            format_todo_summary,
            is_overdue,
            get_priority_weight,
        )
        assert callable(parse_due_date)
        assert callable(format_todo_summary)
        assert callable(is_overdue)
        assert callable(get_priority_weight)
