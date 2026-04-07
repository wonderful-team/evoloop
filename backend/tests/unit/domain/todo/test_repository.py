"""
Test Todo Repository - Data access layer
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.domain.todo.repository import TodoRepository, TodoRepositorySync
from app.domain.todo.schemas import TodoCreateInternal, TodoFilter, TodoUpdate
from app.models.todo import TodoItem, TodoStatus, TodoPriority


@pytest.fixture
def mock_session():
    """Create mock async database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_sync_session():
    """Create mock sync database session."""
    session = Mock()
    return session


@pytest.fixture
def sample_todo_data():
    """Create sample todo data."""
    return TodoCreateInternal(
        title="Test Todo",
        description="Test Description",
        priority=TodoPriority.MEDIUM,
        category="test",
        due_date=None,
        project_id=1,
        source_conversation_id="conv-123",
        source_message_id="msg-456",
    )


class TestTodoRepositoryCreate:
    """Test repository create operations."""
    
    @pytest.mark.asyncio
    async def test_create_todo(self, mock_session, sample_todo_data):
        """Test creating a todo."""
        repo = TodoRepository(mock_session)
        
        # Mock the session behavior
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        result = await repo.create(sample_todo_data)
        
        assert isinstance(result, TodoItem)
        assert result.title == "Test Todo"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()


class TestTodoRepositoryGet:
    """Test repository retrieval operations."""
    
    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_session):
        """Test getting existing todo by ID."""
        repo = TodoRepository(mock_session)
        
        # Create mock todo
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "test-id"
        
        # Mock execute result
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_todo)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await repo.get_by_id("test-id")
        
        assert result == mock_todo
        mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_session):
        """Test getting non-existent todo returns None."""
        repo = TodoRepository(mock_session)
        
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await repo.get_by_id("non-existent")
        
        assert result is None


class TestTodoRepositoryList:
    """Test repository list operations."""
    
    @pytest.mark.asyncio
    async def test_list_all(self, mock_session):
        """Test listing all todos."""
        repo = TodoRepository(mock_session)
        
        mock_todos = [Mock(spec=TodoItem), Mock(spec=TodoItem)]
        mock_result = Mock()
        mock_result.scalars.return_value.all = Mock(return_value=mock_todos)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        results = await repo.list_todos(TodoFilter(limit=10))
        
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, mock_session):
        """Test listing with status filter."""
        repo = TodoRepository(mock_session)
        
        mock_result = Mock()
        mock_result.scalars.return_value.all = Mock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        results = await repo.list_todos(
            TodoFilter(status=TodoStatus.PENDING)
        )
        
        # Verify query was built with filter
        mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_with_project_filter(self, mock_session):
        """Test listing with project filter."""
        repo = TodoRepository(mock_session)
        
        mock_result = Mock()
        mock_result.scalars.return_value.all = Mock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        results = await repo.list_todos(TodoFilter(project_id=123))
        
        mock_session.execute.assert_called_once()


class TestTodoRepositoryCount:
    """Test repository count operations."""
    
    @pytest.mark.asyncio
    async def test_count_todos(self, mock_session):
        """Test counting todos."""
        repo = TodoRepository(mock_session)
        
        mock_result = Mock()
        mock_result.scalar = Mock(return_value=42)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        count = await repo.count_todos()
        
        assert count == 42


class TestTodoRepositoryUpdate:
    """Test repository update operations."""
    
    @pytest.mark.asyncio
    async def test_update_todo(self, mock_session):
        """Test updating a todo."""
        repo = TodoRepository(mock_session)
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.title = "Old Title"
        
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        result = await repo.update(
            mock_todo,
            TodoUpdate(title="New Title")
        )
        
        assert mock_todo.title == "New Title"
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_mark_status(self, mock_session):
        """Test marking todo status."""
        repo = TodoRepository(mock_session)
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.status = TodoStatus.PENDING
        
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        result = await repo.mark_status(mock_todo, TodoStatus.COMPLETED)
        
        assert mock_todo.status == TodoStatus.COMPLETED


class TestTodoRepositoryDelete:
    """Test repository delete operations."""
    
    @pytest.mark.asyncio
    async def test_delete_todo(self, mock_session):
        """Test deleting a todo."""
        repo = TodoRepository(mock_session)
        
        mock_todo = Mock(spec=TodoItem)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        
        await repo.delete(mock_todo)
        
        mock_session.delete.assert_called_once_with(mock_todo)
        mock_session.commit.assert_called_once()


class TestTodoRepositoryCleanup:
    """Test repository cleanup operations."""
    
    @pytest.mark.asyncio
    async def test_delete_by_message_ids(self, mock_session):
        """Test deleting by message IDs."""
        repo = TodoRepository(mock_session)
        
        mock_result = Mock()
        mock_result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        
        count = await repo.delete_by_message_ids(["msg1", "msg2"])
        
        assert count == 5
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


class TestTodoRepositorySync:
    """Test synchronous repository."""
    
    def test_sync_create(self, sample_todo_data):
        """Test synchronous creation."""
        repo = TodoRepositorySync()
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "sync-id"
        mock_todo.title = sample_todo_data.title
        
        with patch('app.domain.todo.repository.session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.refresh = Mock()
            
            # Create should create new TodoItem
            result = repo.create_sync(sample_todo_data)
            
            # Verify the session operations were called
            assert isinstance(result, TodoItem)
    
    def test_sync_get_by_id_found(self):
        """Test synchronous get by ID found."""
        repo = TodoRepositorySync()
        
        mock_todo = Mock(spec=TodoItem)
        mock_todo.id = "test-id"
        
        with patch('app.domain.todo.repository.session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
            mock_result = Mock()
            mock_result.scalar_one_or_none = Mock(return_value=mock_todo)
            mock_session.execute = Mock(return_value=mock_result)
            
            result = repo.get_by_id_sync("test-id")
            
            assert result.id == "test-id"
    
    def test_sync_list_todos(self):
        """Test synchronous list."""
        repo = TodoRepositorySync()
        
        with patch('app.domain.todo.repository.session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
            mock_result = Mock()
            mock_result.scalars.return_value.all = Mock(return_value=[])
            mock_session.execute = Mock(return_value=mock_result)
            
            results = repo.list_todos_sync(TodoFilter(limit=10))
            
            assert results == []
