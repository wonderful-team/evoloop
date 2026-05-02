"""Schemas for tools module."""

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


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


class TaskResult(DynamicBaseModel):
    success: bool = True
    output: str = ""
    exit_code: int | None = None
    data: Any = None


class EvoLoopToolConfig(DynamicBaseModel):
    """Configuration for EvoLoop tool metadata injected by the @evoloop_tool decorator."""
    is_pollable: bool = False
    is_state_mutating: bool = False
    affected_path_keys: list[str] = Field(default_factory=list)
    summary_template: str | None = None
    result_summary_template: str | None = None
    is_memory_tool: bool = False
    is_multimodal: bool = False
    is_hidden: bool = False
    handle_tool_error: bool = True
    is_hitl: bool = False  # If True, this tool triggers a human-in-the-loop request
    required_benefit: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.affected_path_keys is None:
            self.affected_path_keys = []


class CacheKey(BaseModel):
    """Immutable cache key with content verification."""
    model_config = ConfigDict(frozen=True)

    tool_name: str
    args_hash: str
    content_hash: str = ""  # File content hash for verification

    def __hash__(self):
        return hash((self.tool_name, self.args_hash, self.content_hash))


class CacheEntry(DynamicBaseModel):
    """Cache entry with metadata."""
    result: Any
    timestamp: float = Field(default_factory=time.time)
    access_count: int = 0
    last_verified: float = 0.0


class CacheStats(DynamicBaseModel):
    """Cache statistics."""
    hits: int
    misses: int
    hit_rate: str
    verifications: int
    invalidations: int
    cache_size: int
    max_size: int


class ToolRegistryMetadata(DynamicBaseModel):
    """Metadata for a tool, merging registry and system fallback data."""
    affected_path_keys: list[str] = Field(default_factory=list)
    result_summary_template: str | None = None
    is_state_mutating: bool = False
    is_pollable: bool = False
    description: str = ""
    is_hidden: bool = False
    summary_template: str | None = None  # Legacy support for i18n
    is_memory_tool: bool = False
    is_hitl: bool = False
