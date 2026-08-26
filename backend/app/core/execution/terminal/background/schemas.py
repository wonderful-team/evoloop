"""Background task schemas for the terminal execution stack."""

from enum import Enum

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class TaskStatus(str, Enum):
    """Task lifecycle states."""

    PENDING = "pending"  # Created but not started
    RUNNING = "running"  # Actively executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Error occurred
    CANCELLED = "cancelled"  # User cancelled
    TIMEOUT = "timeout"  # Exceeded time limit


class TaskType(str, Enum):
    """Types of background tasks - determines execution strategy."""

    COMMAND = "command"  # Shell commands (npm build, docker)
    BROWSER = "browser"  # Browser automation
    MOBILE = "mobile"  # Mobile automation
    DESKTOP = "desktop"  # Desktop automation
    FILE_OPERATION = "file_op"  # Large file operations
    SEARCH = "search"  # Long-running search
    BUILD = "build"  # Build tasks
    TEST = "test"  # Test execution
    CUSTOM = "custom"  # User-defined tasks


class TaskMetadata(DynamicBaseModel):
    shell_env: dict[str, str] = Field(default_factory=dict)
    browser_profile: str | None = None
    device_id: str | None = None
    working_directory: str | None = None


class CreateBackgroundTaskRequest(DynamicBaseModel):
    """Request model for creating a background task."""

    task_type: TaskType
    title: str
    tool_name: str
    thread_id: str
    description: str = ""
    project_id: int | None = None
    timeout_seconds: int = 3600
    metadata: TaskMetadata | None = None


class BackgroundTaskManagerStats(DynamicBaseModel):
    """Background task manager statistics."""

    total_tasks: int
    by_status: dict[str, int]
    by_thread: int
    by_tool: dict[str, int]
