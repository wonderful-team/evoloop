"""
Test Todo Utils - Date parsing and formatting utilities
"""
import pytest
from datetime import datetime, timedelta
from app.domain.todo.utils import (
    parse_due_date,
    format_todo_summary,
    is_overdue,
    get_priority_weight,
    should_remind,
    get_status_transition_allowed,
)
from app.models.todo import TodoStatus, TodoPriority, TodoItem
from app.utils.time import utcnow


class TestParseDueDate:
    """Test date parsing functionality."""
    
    def test_none_returns_none(self):
        """Test None returns None."""
        assert parse_due_date(None) is None
    
    def test_empty_string_returns_none(self):
        """Test empty string returns None."""
        assert parse_due_date("") is None
    
    def test_tbd_keywords(self):
        """Test TBD keywords return None."""
        for keyword in ["待定", "tbd", "none", "null", "pending", "unset"]:
            assert parse_due_date(keyword) is None, f"Failed for {keyword}"
    
    def test_datetime_pass_through(self):
        """Test datetime passes through unchanged."""
        now = datetime.now()
        assert parse_due_date(now) == now
    
    def test_iso_format(self):
        """Test ISO format parsing."""
        result = parse_due_date("2024-12-31T23:59:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 31
    
    def test_relative_hours(self):
        """Test relative hours parsing."""
        before = utcnow()
        result = parse_due_date("2 hours")
        after = utcnow()
        
        assert result is not None
        # Should be approximately 2 hours from now
        expected_min = before + timedelta(hours=2)
        expected_max = after + timedelta(hours=2)
        assert expected_min <= result <= expected_max
    
    def test_relative_minutes(self):
        """Test relative minutes parsing."""
        result = parse_due_date("30 mins")
        assert result is not None
        # Should be approximately 30 minutes from now
        now = utcnow()
        diff = abs((result - now).total_seconds() - 1800)
        assert diff < 5  # Within 5 seconds
    
    def test_relative_days(self):
        """Test relative days parsing."""
        result = parse_due_date("3 days")
        assert result is not None
        now = utcnow()
        assert timedelta(days=2) < result - now < timedelta(days=4)
    
    def test_relative_weeks(self):
        """Test relative weeks parsing."""
        result = parse_due_date("1 week")
        assert result is not None
        now = utcnow()
        assert timedelta(days=6) < result - now < timedelta(days=8)
    
    def test_tomorrow(self):
        """Test tomorrow keyword."""
        result = parse_due_date("tomorrow")
        assert result is not None
        now = utcnow()
        assert timedelta(hours=23) < result - now < timedelta(hours=25)
    
    def test_today(self):
        """Test today keyword."""
        result = parse_due_date("today")
        assert result is not None
        now = utcnow()
        # Should be very close to now
        assert abs((result - now).total_seconds()) < 2
    
    def test_chinese_formats(self):
        """Test Chinese date formats."""
        result = parse_due_date("2小时")
        assert result is not None
        
        result = parse_due_date("明天")
        assert result is not None
    
    def test_invalid_format_returns_none(self):
        """Test invalid format returns None."""
        assert parse_due_date("invalid date format") is None


class TestFormatTodoSummary:
    """Test todo summary formatting."""
    
    def test_pending_todo(self):
        """Test pending todo formatting."""
        todo = {"title": "Test Task", "status": TodoStatus.PENDING, "priority": TodoPriority.MEDIUM}
        result = format_todo_summary(todo)
        assert "○" in result
        assert "Test Task" in result
    
    def test_completed_todo(self):
        """Test completed todo formatting."""
        todo = {"title": "Done Task", "status": TodoStatus.COMPLETED, "priority": TodoPriority.LOW}
        result = format_todo_summary(todo)
        assert "✓" in result
        assert "Done Task" in result
    
    def test_cancelled_todo(self):
        """Test cancelled todo formatting."""
        todo = {"title": "Cancelled Task", "status": TodoStatus.CANCELLED, "priority": TodoPriority.LOW}
        result = format_todo_summary(todo)
        assert "✗" in result
    
    def test_high_priority_marker(self):
        """Test high priority shows marker."""
        todo = {"title": "Urgent", "status": TodoStatus.PENDING, "priority": TodoPriority.HIGH}
        result = format_todo_summary(todo)
        assert "[!]" in result
    
    def test_due_date_included(self):
        """Test due date is included in summary."""
        due = datetime(2024, 12, 31, 23, 59)
        todo = {
            "title": "Deadline Task",
            "status": TodoStatus.PENDING,
            "priority": TodoPriority.MEDIUM,
            "due_date": due
        }
        result = format_todo_summary(todo)
        assert "2024-12-31" in result
    
    def test_object_input(self):
        """Test with object instead of dict."""
        class MockTodo:
            title = "Mock"
            status = TodoStatus.PENDING
            priority = TodoPriority.MEDIUM
            due_date = None
        
        result = format_todo_summary(MockTodo())
        assert "Mock" in result


class TestIsOverdue:
    """Test overdue detection."""
    
    def test_no_due_date_not_overdue(self):
        """Test no due date means not overdue."""
        todo = {"due_date": None, "status": TodoStatus.PENDING}
        assert is_overdue(todo) is False
    
    def test_completed_not_overdue(self):
        """Test completed todo is not overdue."""
        past = utcnow() - timedelta(days=1)
        todo = {"due_date": past, "status": TodoStatus.COMPLETED}
        assert is_overdue(todo) is False
    
    def test_cancelled_not_overdue(self):
        """Test cancelled todo is not overdue."""
        past = utcnow() - timedelta(days=1)
        todo = {"due_date": past, "status": TodoStatus.CANCELLED}
        assert is_overdue(todo) is False
    
    def test_future_not_overdue(self):
        """Test future due date is not overdue."""
        future = utcnow() + timedelta(days=1)
        todo = {"due_date": future, "status": TodoStatus.PENDING}
        assert is_overdue(todo) is False
    
    def test_past_is_overdue(self):
        """Test past due date is overdue."""
        past = utcnow() - timedelta(days=1)
        todo = {"due_date": past, "status": TodoStatus.PENDING}
        assert is_overdue(todo) is True


class TestGetPriorityWeight:
    """Test priority weight mapping."""
    
    def test_high_priority(self):
        """Test high priority weight."""
        assert get_priority_weight("high") == 3
        assert get_priority_weight(TodoPriority.HIGH) == 3
    
    def test_medium_priority(self):
        """Test medium priority weight."""
        assert get_priority_weight("medium") == 2
        assert get_priority_weight(TodoPriority.MEDIUM) == 2
    
    def test_low_priority(self):
        """Test low priority weight."""
        assert get_priority_weight("low") == 1
        assert get_priority_weight(TodoPriority.LOW) == 1
    
    def test_default_weight(self):
        """Test default weight for unknown."""
        assert get_priority_weight("unknown") == 2
        assert get_priority_weight(None) == 2


class TestShouldRemind:
    """Test reminder logic."""
    
    def test_pending_with_past_due_reminds(self):
        """Test pending todo with past due date should remind."""
        past = utcnow() - timedelta(minutes=5)
        todo = {"due_date": past, "status": TodoStatus.PENDING}
        assert should_remind(todo) is True
    
    def test_pending_with_future_due_no_remind(self):
        """Test pending todo with future due date should not remind."""
        future = utcnow() + timedelta(hours=1)
        todo = {"due_date": future, "status": TodoStatus.PENDING}
        assert should_remind(todo) is False
    
    def test_completed_no_remind(self):
        """Test completed todo should not remind."""
        past = utcnow() - timedelta(hours=1)
        todo = {"due_date": past, "status": TodoStatus.COMPLETED}
        assert should_remind(todo) is False
    
    def test_with_offset(self):
        """Test reminder with offset."""
        future = utcnow() + timedelta(minutes=5)
        todo = {"due_date": future, "status": TodoStatus.PENDING}
        # With 10 minute offset, should remind (5 < 10)
        assert should_remind(todo, reminder_offset_minutes=10) is True


class TestGetStatusTransitionAllowed:
    """Test status transition rules."""
    
    def test_pending_to_completed(self):
        """Test pending can go to completed."""
        assert get_status_transition_allowed(
            TodoStatus.PENDING, TodoStatus.COMPLETED
        ) is True
    
    def test_pending_to_cancelled(self):
        """Test pending can go to cancelled."""
        assert get_status_transition_allowed(
            TodoStatus.PENDING, TodoStatus.CANCELLED
        ) is True
    
    def test_completed_to_pending(self):
        """Test completed can reopen to pending."""
        assert get_status_transition_allowed(
            TodoStatus.COMPLETED, TodoStatus.PENDING
        ) is True
    
    def test_cancelled_to_pending(self):
        """Test cancelled can reopen to pending."""
        assert get_status_transition_allowed(
            TodoStatus.CANCELLED, TodoStatus.PENDING
        ) is True
    
    def test_completed_to_cancelled_not_allowed(self):
        """Test completed cannot go directly to cancelled."""
        assert get_status_transition_allowed(
            TodoStatus.COMPLETED, TodoStatus.CANCELLED
        ) is False
