"""
Test Todo Service - Business logic layer
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.domain.todo import (
    TodoService,
    TodoServiceSync,
    TodoCreate,
    TodoUpdate,
    TodoFilter,
    TodoNotFoundError,
    TodoValidationError,
)
from app.domain.todo.service import get_todo_service, get_todo_service_sync
from app.models.todo import TodoItem, TodoStatus, TodoPriority


@pytest.fixture
def mock_session():
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_todo():
    """Create mock todo item."""
    todo = Mock(spec=TodoItem)
    todo.id = "test-id-123"
    todo.title = "Test Todo"
    todo.description = "Test Description"
    todo.status = TodoStatus.PENDING
    todo.priority = TodoPriority.MEDIUM
    todo.category = None
    todo.due_date = None
    todo.project_id = None
    todo.source_conversation_id = None
    todo.source_message_id = None
    todo.created_at = datetime.now()
    todo.updated_at = datetime.now()
    todo.priority.value = "medium"
    todo.status.value = "pending"
    return todo


class TestTodoServiceCreation:
    """Test TodoService creation methods."""
    
    @pytest.mark.asyncio
    async def test_create_success(self, mock_session):
        """Test successful todo creation."""
        service = TodoService(mock_session)
        
        # Mock repository
        with patch.object(service, 'repository') as mock_repo:
            mock_todo = Mock(spec=TodoItem)
            mock_todo.id = "new-id"
            mock_todo.title = "New Todo"
            mock_todo.priority = TodoPriority.HIGH
            mock_todo.priority.value = "high"
            mock_repo.create = AsyncMock(return_value=mock_todo)
            
            result = await service.create(
                TodoCreate(title="New Todo", priority="high")
            )
            
            assert result.title == "New Todo"
            mock_repo.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_empty_title_raises(self, mock_session):
        """Test creation with empty title raises error."""
        service = TodoService(mock_session)
        
        with pytest.raises(TodoValidationError):
            await service.create(TodoCreate(title=""))
    
    @pytest.mark.asyncio
    async def test_create_whitespace_title_raises(self, mock_session):
        """Test creation with whitespace-only title raises error."""
        service = TodoService(mock_session)
        
        with pytest.raises(TodoValidationError):
            await service.create(TodoCreate(title="   "))
    
    @pytest.mark.asyncio
    async def test_create_with_due_date_string(self, mock_session):
        """Test creation with string due date."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_todo = Mock(spec=TodoItem)
            mock_todo.id = "new-id"
            mock_todo.title = "Todo with Due"
            mock_todo.priority = TodoPriority.MEDIUM
            mock_todo.priority.value = "medium"
            mock_repo.create = AsyncMock(return_value=mock_todo)
            
            result = await service.create(
                TodoCreate(title="Todo with Due", due_date="1 hour")
            )
            
            assert result.title == "Todo with Due"


class TestTodoServiceRetrieval:
    """Test TodoService retrieval methods."""
    
    @pytest.mark.asyncio
    async def test_get_by_id_success(self, mock_session, mock_todo):
        """Test successful retrieval by ID."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=mock_todo)
            
            result = await service.get_by_id("test-id-123")
            
            assert result.id == "test-id-123"
            assert result.title == "Test Todo"
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_session):
        """Test retrieval of non-existent todo raises error."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=None)
            
            with pytest.raises(TodoNotFoundError):
                await service.get_by_id("non-existent-id")
    
    @pytest.mark.asyncio
    async def test_list_todos(self, mock_session, mock_todo):
        """Test listing todos."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.list_todos = AsyncMock(return_value=[mock_todo])
            
            results = await service.list_todos(TodoFilter(limit=10))
            
            assert len(results) == 1
            assert results[0].id == "test-id-123"


class TestTodoServiceUpdate:
    """Test TodoService update methods."""
    
    @pytest.mark.asyncio
    async def test_update_success(self, mock_session, mock_todo):
        """Test successful update."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=mock_todo)
            mock_repo.update = AsyncMock(return_value=mock_todo)
            
            result = await service.update(
                "test-id-123",
                TodoUpdate(title="Updated Title")
            )
            
            mock_repo.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_not_found(self, mock_session):
        """Test update of non-existent todo raises error."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=None)
            
            with pytest.raises(TodoNotFoundError):
                await service.update("non-existent", TodoUpdate())
    
    @pytest.mark.asyncio
    async def test_mark_completed_success(self, mock_session, mock_todo):
        """Test marking todo as completed."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=mock_todo)
            mock_repo.mark_status = AsyncMock(return_value=mock_todo)
            
            result = await service.mark_completed("test-id-123")
            
            mock_repo.mark_status.assert_called_once_with(
                mock_todo, TodoStatus.COMPLETED
            )
    
    @pytest.mark.asyncio
    async def test_mark_cancelled_success(self, mock_session, mock_todo):
        """Test marking todo as cancelled."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=mock_todo)
            mock_repo.mark_status = AsyncMock(return_value=mock_todo)
            
            result = await service.mark_cancelled("test-id-123")
            
            mock_repo.mark_status.assert_called_once_with(
                mock_todo, TodoStatus.CANCELLED
            )


class TestTodoServiceDeletion:
    """Test TodoService deletion methods."""
    
    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session, mock_todo):
        """Test successful deletion."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=mock_todo)
            mock_repo.delete = AsyncMock(return_value=None)
            
            await service.delete("test-id-123")
            
            mock_repo.delete.assert_called_once_with(mock_todo)
    
    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_session):
        """Test deletion of non-existent todo raises error."""
        service = TodoService(mock_session)
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.get_by_id = AsyncMock(return_value=None)
            
            with pytest.raises(TodoNotFoundError):
                await service.delete("non-existent")


class TestTodoServiceSync:
    """Test synchronous TodoService."""
    
    def test_sync_create(self):
        """Test synchronous creation."""
        service = TodoServiceSync()
        
        with patch.object(service, 'repository') as mock_repo:
            mock_todo = Mock(spec=TodoItem)
            mock_todo.id = "sync-id"
            mock_todo.title = "Sync Todo"
            mock_todo.priority = TodoPriority.MEDIUM
            mock_repo.create_sync = Mock(return_value=mock_todo)
            
            result = service.create(TodoCreate(title="Sync Todo"))
            
            assert result.title == "Sync Todo"
    
    def test_sync_list(self):
        """Test synchronous list."""
        service = TodoServiceSync()
        
        with patch.object(service, 'repository') as mock_repo:
            mock_repo.list_todos_sync = Mock(return_value=[])
            
            results = service.list_todos()
            
            assert results == []
    
    def test_sync_mark_completed(self):
        """Test synchronous mark completed."""
        service = TodoServiceSync()
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "test-id"
        mock_todo.title = "Test"
        mock_todo.status = TodoStatus.COMPLETED
        
        with patch('app.domain.todo.service.session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
            # Mock the query result
            mock_result = Mock()
            mock_result.scalar_one_or_none = Mock(return_value=mock_todo)
            mock_session.execute = Mock(return_value=mock_result)
            
            result = service.mark_completed("test-id")
            
            assert result.status == TodoStatus.COMPLETED
    
    def test_sync_format_list_empty(self):
        """Test formatting empty list."""
        service = TodoServiceSync()
        
        result = service.format_todo_list([])
        
        assert "No todos" in result or "未找到" in result


class TestFactoryFunctions:
    """Test factory functions."""
    
    def test_get_todo_service(self, mock_session):
        """Test async service factory."""
        service = get_todo_service(mock_session)
        assert isinstance(service, TodoService)
        assert service.session == mock_session
    
    def test_get_todo_service_sync(self):
        """Test sync service factory."""
        service = get_todo_service_sync()
        assert isinstance(service, TodoServiceSync)
