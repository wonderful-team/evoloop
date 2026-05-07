"""
Test Todo Schemas - Pydantic DTO validation
"""
import pytest
from datetime import datetime
from app.domain.todo.schemas import (
    TodoCreate,
    TodoCreateInternal,
    TodoUpdate,
    TodoResponse,
    TodoFilter,
    TodoBase,
)
from app.models.todo import TodoPriority, TodoStatus


class TestTodoCreate:
    """Test TodoCreate schema validation."""
    
    def test_valid_creation(self):
        """Test valid todo creation."""
        todo = TodoCreate(title="Test Todo")
        assert todo.title == "Test Todo"
        assert todo.priority == TodoPriority.MEDIUM
        assert todo.description is None
    
    def test_title_required(self):
        """Test title is required."""
        with pytest.raises(ValueError):
            TodoCreate()
    
    def test_title_min_length(self):
        """Test title minimum length."""
        with pytest.raises(ValueError):
            TodoCreate(title="")  # Empty string
    
    def test_title_max_length(self):
        """Test title maximum length."""
        with pytest.raises(ValueError):
            TodoCreate(title="x" * 256)  # Too long
    
    def test_priority_string(self):
        """Test priority can be string."""
        todo = TodoCreate(title="Test", priority="high")
        assert todo.priority == "high"
    
    def test_priority_enum(self):
        """Test priority can be enum."""
        todo = TodoCreate(title="Test", priority=TodoPriority.HIGH)
        assert todo.priority == TodoPriority.HIGH
    
    def test_due_date_string(self):
        """Test due_date can be string."""
        todo = TodoCreate(title="Test", due_date="1 hour")
        assert todo.due_date == "1 hour"
    
    def test_due_date_datetime(self):
        """Test due_date can be datetime."""
        now = datetime.now()
        todo = TodoCreate(title="Test", due_date=now)
        assert todo.due_date == now
    
    def test_category_max_length(self):
        """Test category maximum length."""
        with pytest.raises(ValueError):
            TodoCreate(title="Test", category="x" * 51)


class TestTodoUpdate:
    """Test TodoUpdate schema validation."""
    
    def test_empty_update(self):
        """Test empty update is valid."""
        update = TodoUpdate()
        assert update.title is None
        assert update.status is None
    
    def test_partial_update(self):
        """Test partial update."""
        update = TodoUpdate(status=TodoStatus.COMPLETED)
        assert update.status == TodoStatus.COMPLETED
        assert update.title is None
    
    def test_status_string(self):
        """Test status can be string."""
        update = TodoUpdate(status="completed")
        assert update.status == "completed"
    
    def test_status_enum(self):
        """Test status can be enum."""
        update = TodoUpdate(status=TodoStatus.CANCELLED)
        assert update.status == TodoStatus.CANCELLED


class TestTodoFilter:
    """Test TodoFilter schema validation."""
    
    def test_default_filter(self):
        """Test default filter values."""
        filter_ = TodoFilter()
        assert filter_.limit == 50
        assert filter_.offset == 0
        assert filter_.order_by == "created_at"
        assert filter_.order_desc is True
        assert filter_.status is None
    
    def test_custom_filter(self):
        """Test custom filter values."""
        filter_ = TodoFilter(
            status=TodoStatus.PENDING,
            project_id=123,
            limit=10,
            offset=20,
        )
        assert filter_.status == TodoStatus.PENDING
        assert filter_.project_id == 123
        assert filter_.limit == 10
        assert filter_.offset == 20
    
    def test_limit_bounds(self):
        """Test limit boundaries."""
        with pytest.raises(ValueError):
            TodoFilter(limit=0)  # Too small
        with pytest.raises(ValueError):
            TodoFilter(limit=101)  # Too large
    
    def test_offset_negative(self):
        """Test offset cannot be negative."""
        with pytest.raises(ValueError):
            TodoFilter(offset=-1)


class TestTodoCreateInternal:
    """Test TodoCreateInternal schema."""
    
    def test_internal_creation(self):
        """Test internal creation schema."""
        todo = TodoCreateInternal(
            title="Internal Test",
            priority=TodoPriority.HIGH,
            project_id=1,
        )
        assert todo.title == "Internal Test"
        assert todo.priority == TodoPriority.HIGH
        assert todo.project_id == 1


class TestTodoResponse:
    """Test TodoResponse schema."""
    
    def test_response_structure(self):
        """Test response has all required fields."""
        now = datetime.now()
        response = TodoResponse(
            id="test-id-123",
            title="Test",
            description=None,
            status=TodoStatus.PENDING,
            priority=TodoPriority.MEDIUM,
            category=None,
            due_date=None,
            source_conversation_id=None,
            source_message_id=None,
            run_id=None,
            project_id=None,
            created_at=now,
            updated_at=now,
        )
        assert response.id == "test-id-123"
        assert response.status == TodoStatus.PENDING
