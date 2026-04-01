"""
Data models for background task management.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"           # Created but not started
    RUNNING = "running"           # Actively executing
    COMPLETED = "completed"       # Successfully finished
    FAILED = "failed"             # Error occurred
    CANCELLED = "cancelled"       # User cancelled
    TIMEOUT = "timeout"           # Exceeded time limit


class TaskType(str, Enum):
    """Types of background tasks - determines execution strategy."""
    COMMAND = "command"           # Shell commands (npm build, docker)
    BROWSER = "browser"           # Browser automation
    MOBILE = "mobile"             # Mobile automation
    DESKTOP = "desktop"           # Desktop automation
    FILE_OPERATION = "file_op"    # Large file operations
    SEARCH = "search"             # Long-running search
    BUILD = "build"               # Build tasks
    TEST = "test"                 # Test execution
    CUSTOM = "custom"             # User-defined tasks


@dataclass
class BackgroundTask:
    """
    Represents a background task instance.
    
    This is a value object - once created, it's stored in TaskManager.
    All mutable operations go through TaskManager.
    
    Attributes:
        task_id: Unique identifier (e.g., "cmd-a1b2c3d4")
        task_type: Category of task
        status: Current lifecycle state
        title: Human-readable description
        description: Detailed description (optional)
        
        tool_name: Which tool created this task
        thread_id: Which conversation/thread owns this task
        project_id: Optional project association
        
        process_id: OS process ID (for cancellation)
        
        created_at: When task was created
        started_at: When execution began
        completed_at: When execution finished
        timeout_seconds: Maximum allowed execution time
        
        output_buffer: Recent output lines (circular buffer)
        result: Final result data (if completed)
        error_message: Error details (if failed)
        
        metadata: Tool-specific data
    """
    # Identity
    task_id: str
    task_type: TaskType
    
    # State
    status: TaskStatus = TaskStatus.PENDING
    title: str = ""
    description: str = ""
    
    # Ownership
    tool_name: str = ""
    thread_id: str = ""
    project_id: Optional[int] = None
    
    # Execution
    process_id: Optional[int] = None
    timeout_seconds: int = 3600  # Default 1 hour max
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Output
    output_buffer: deque = field(default_factory=lambda: deque(maxlen=1000))
    result: Any = None
    error_message: Optional[str] = None
    
    # Extension point for tool-specific data
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Internal: cancellation callback
    _cancel_fn: Optional[Callable[[], None]] = field(default=None, repr=False)
    
    def to_dict(self, include_output: bool = True, output_lines: int = 50) -> Dict:
        """Convert to dictionary for API responses."""
        data = {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "tool_name": self.tool_name,
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "process_id": self.process_id,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "elapsed_seconds": self.elapsed_seconds,
            "is_completed": self.is_completed,
            "is_running": self.is_running,
            "can_cancel": self.can_cancel,
        }
        
        if include_output:
            data["output"] = self.get_recent_output(output_lines)
            data["output_line_count"] = len(self.output_buffer)
        
        if self.error_message:
            data["error_message"] = self.error_message
            
        if self.result is not None:
            data["result"] = self._serialize_result()
            
        return data
    
    def get_recent_output(self, n: int = 50) -> str:
        """Get last n lines of output."""
        lines = list(self.output_buffer)
        return "\n".join(lines[-n:])
    
    def append_output(self, output: str) -> None:
        """Append output line(s)."""
        if output:
            self.output_buffer.append(output.rstrip("\n"))
    
    @property
    def elapsed_seconds(self) -> int:
        """Calculate elapsed time."""
        end_time = self.completed_at or datetime.now()
        start_time = self.started_at or self.created_at
        return int((end_time - start_time).total_seconds())
    
    @property
    def is_completed(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        }
    
    @property
    def is_running(self) -> bool:
        """Check if task is actively running."""
        return self.status == TaskStatus.RUNNING
    
    @property
    def can_cancel(self) -> bool:
        """Check if task can be cancelled."""
        return self.status in {TaskStatus.PENDING, TaskStatus.RUNNING}
    
    def _serialize_result(self) -> Any:
        """Safely serialize result."""
        if isinstance(self.result, (str, int, float, bool, type(None))):
            return self.result
        if isinstance(self.result, dict):
            return self.result
        if isinstance(self.result, list):
            return self.result[:100]  # Limit array size
        return str(self.result)[:1000]  # Fallback to string
    
    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for cancellation."""
        self._cancel_fn = callback
    
    async def cancel(self) -> bool:
        """
        Cancel this task.
        
        Returns:
            True if cancellation was initiated, False otherwise.
        """
        if not self.can_cancel:
            return False
        
        self.status = TaskStatus.CANCELLED
        
        if self._cancel_fn:
            try:
                if asyncio.iscoroutinefunction(self._cancel_fn):
                    await self._cancel_fn()
                else:
                    self._cancel_fn()
            except Exception as e:
                # Log but don't fail
                import logging
                logging.getLogger(__name__).warning(f"Cancel callback failed: {e}")
        
        self.completed_at = datetime.now()
        return True


import asyncio  # For type checking in cancel method
