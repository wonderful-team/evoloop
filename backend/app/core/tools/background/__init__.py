"""
Background Task Management for EvoLoop Tools.

Provides lightweight task management for long-running tool operations.
This is a pragmatic implementation - not a full job queue system.

Usage:
    from app.core.tools.background import BackgroundTaskManager, TaskType

    # Create task
    task = await task_manager.create_task(
        task_type=TaskType.COMMAND,
        title="npm run build",
        thread_id="thread-123",
    )

    # Execute in background
    asyncio.create_task(run_command_background(task, command))

    # Query status
    status = task_manager.get_task(task.task_id)
"""

from .manager import BackgroundTaskManager, CreateBackgroundTaskRequest
from .models import BackgroundTask, TaskStatus, TaskType

task_manager = BackgroundTaskManager()

__all__ = [
    "BackgroundTaskManager",
    "BackgroundTask",
    "TaskStatus",
    "TaskType",
    "task_manager",
    "CreateBackgroundTaskRequest",
]
