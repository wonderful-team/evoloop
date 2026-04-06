"""
Todo Domain Utilities - Todo-specific helper functions.

This module provides Todo-specific utilities that build upon
common utilities from app.utils.
"""
from datetime import datetime

from app.models.todo import TodoStatus
from app.utils import is_past, parse_relative_time, utcnow

# Re-export parse_relative_time for domain convenience
parse_due_date = parse_relative_time
"""
Parse due date from various formats.

Re-exports parse_relative_time from app.utils.time for domain consistency.
Supports datetime, ISO format, relative time ("1 hour"), Chinese ("明天"), etc.

See app.utils.time.parse_relative_time for full documentation.
"""


def format_todo_summary(todo) -> str:
    """
    Format a single Todo as a summary string.
    
    This is Todo-specific formatting logic, using Todo status icons
    and priority markers.
    
    Args:
        todo: TodoItem instance or dict with todo fields
        
    Returns:
        Formatted summary string like "✓ [!] Review PR (Due: 2024-01-15)"
    """
    if isinstance(todo, dict):
        title = todo.get("title", "Unknown")
        status = todo.get("status", "?")
        priority = todo.get("priority", "?")
        due_date = todo.get("due_date")
    else:
        title = getattr(todo, "title", "Unknown")
        status = getattr(todo, "status", "?")
        priority = getattr(todo, "priority", "?")
        due_date = getattr(todo, "due_date", None)
    
    # Status icons specific to Todo domain
    status_icon = {
        TodoStatus.COMPLETED: "✓",
        TodoStatus.CANCELLED: "✗",
        TodoStatus.PENDING: "○",
    }.get(status, "?")
    
    # Priority markers
    # Handle enum type
    if hasattr(priority, 'value'):
        priority_str = priority.value.lower()
    else:
        priority_str = str(priority).lower()
    
    priority_marker = {
        "high": "[!]",
        "medium": "",
        "low": "",
    }.get(priority_str, "")
    
    # Format due date if present
    due_str = ""
    if due_date:
        if isinstance(due_date, datetime):
            due_str = f" (Due: {due_date.strftime('%Y-%m-%d %H:%M')})"
        else:
            due_str = f" (Due: {due_date})"
    
    parts = [p for p in [status_icon, priority_marker, title + due_str] if p]
    return " ".join(parts)


def is_overdue(todo, reference_time: datetime | None = None) -> bool:
    """
    Check if a Todo is overdue.
    
    A Todo is overdue if:
    - It has a due_date
    - It's not completed or cancelled
    - The due_date is in the past
    
    Args:
        todo: TodoItem instance or dict with due_date and status
        reference_time: Time to compare against (default: utcnow())
        
    Returns:
        True if overdue, False otherwise
    """
    if isinstance(todo, dict):
        due_date = todo.get("due_date")
        status = todo.get("status")
    else:
        due_date = getattr(todo, "due_date", None)
        status = getattr(todo, "status", None)
    
    # Completed or cancelled todos are never overdue
    if status in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]:
        return False
    
    # Use common utility for time comparison
    return is_past(due_date, reference_time or utcnow())


def get_priority_weight(priority) -> int:
    """
    Get numeric weight for priority sorting.
    
    Higher weight = more important. Used for sorting todos
    by priority in listings.
    
    Args:
        priority: TodoPriority enum or string
        
    Returns:
        Weight value (high=3, medium=2, low=1)
        
    Example:
        >>> sorted(todos, key=lambda t: -get_priority_weight(t.priority))
        # Sorted by priority descending
    """
    if priority is None:
        return 2
    
    # Handle enum type - extract value
    if hasattr(priority, 'value'):
        priority_str = priority.value.lower()
    else:
        priority_str = str(priority).lower()
    
    weights = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }
    return weights.get(priority_str, 2)


def should_remind(todo, reminder_offset_minutes: int = 0) -> bool:
    """
    Check if a Todo should trigger a reminder.
    
    Args:
        todo: TodoItem with due_date
        reminder_offset_minutes: Minutes before due_date to trigger
        
    Returns:
        True if reminder should be sent
    """
    if isinstance(todo, dict):
        due_date = todo.get("due_date")
        status = todo.get("status")
    else:
        due_date = getattr(todo, "due_date", None)
        status = getattr(todo, "status", None)
    
    # Only pending todos get reminders
    if status != TodoStatus.PENDING:
        return False
    
    if not due_date:
        return False
    
    from datetime import timedelta
    reminder_time = due_date - timedelta(minutes=reminder_offset_minutes)
    return utcnow() >= reminder_time


def get_status_transition_allowed(current_status: TodoStatus, new_status: TodoStatus) -> bool:
    """
    Check if a status transition is valid.
    
    Defines valid state transitions for Todo workflow:
    - pending -> completed, cancelled
    - completed -> pending (reopen)
    - cancelled -> pending (reopen)
    
    Args:
        current_status: Current TodoStatus
        new_status: Desired new TodoStatus
        
    Returns:
        True if transition is allowed
    """
    allowed_transitions = {
        TodoStatus.PENDING: [TodoStatus.COMPLETED, TodoStatus.CANCELLED],
        TodoStatus.COMPLETED: [TodoStatus.PENDING],  # Can reopen
        TodoStatus.CANCELLED: [TodoStatus.PENDING],  # Can reopen
    }
    return new_status in allowed_transitions.get(current_status, [])
