"""
Background Task Manager - Lightweight task management for EvoLoop.

Design Philosophy:
- Pragmatic: Solves real problems without over-engineering
- Ephemeral: Tasks live in memory, not persisted (by design)
- Scoped: Tasks are bound to threads/conversations
- Observable: Real-time status updates via existing infrastructure

NOT a full job queue (like Celery/RQ). For that, use dedicated task systems.

Typical Usage:
    # Tool creates a background task
    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title="npm run build",
            tool_name="execute_command",
            thread_id=thread_id,
            timeout_seconds=300,
        )
    )
    
    # Tool starts execution
    await task_manager.start_task(task.task_id, process_id=pid)
    
    # Tool appends output
    task_manager.append_output(task.task_id, "Building modules...")
    
    # Tool completes
    await task_manager.complete_task(task.task_id, result={"exit_code": 0})
    
    # Or fails
    await task_manager.fail_task(task.task_id, error="Build failed")
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from app.infrastructure.pydantic_base import DynamicBaseModel
from .models import BackgroundTask, TaskMetadata, TaskStatus, TaskType

logger = logging.getLogger(__name__)


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


class BackgroundTaskManager:
    """
    Manages background tasks for long-running tool operations.
    
    This is a SINGLETON - use the global `task_manager` instance.
    
    Responsibilities:
    1. Task lifecycle management (create, start, complete, fail, cancel)
    2. Task indexing by thread, tool, status
    3. Event publishing for real-time updates
    4. Automatic cleanup of old tasks
    
    NOT Responsible for:
    - Actually executing tasks (tools do that)
    - Persisting tasks (ephemeral by design)
    - Scheduling (no priority queue)
    - Distributed execution (single-node only)
    
    Thread Safety:
    - All public methods are async-safe
    - Internal data structures protected by asyncio.Lock
    """

    _instance: Optional['BackgroundTaskManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Primary storage: task_id -> BackgroundTask
        self._tasks: dict[str, BackgroundTask] = {}

        # Indexes for efficient querying
        self._thread_index: dict[str, set[str]] = {}  # thread_id -> task_ids
        self._tool_index: dict[str, set[str]] = {}    # tool_name -> task_ids
        self._status_index: dict[TaskStatus, set[str]] = {}  # status -> task_ids

        # Concurrency control
        self._data_lock = asyncio.Lock()

        # Configuration
        self._cleanup_interval = 300  # 5 minutes
        self._max_task_age = 3600 * 24  # 24 hours
        self._max_tasks_per_thread = 50  # Prevent memory abuse

        self._initialized = True
        self._cleanup_task: asyncio.Task | None = None

        logger.info("BackgroundTaskManager initialized")

    async def start_cleanup_worker(self):
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Periodically clean up old tasks."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup_old_tasks(self):
        """Remove completed tasks older than max_task_age."""
        cutoff = datetime.now() - timedelta(seconds=self._max_task_age)
        to_remove = []

        async with self._data_lock:
            for task_id, task in self._tasks.items():
                if task.is_completed and task.completed_at and task.completed_at < cutoff:
                    to_remove.append(task_id)

            for task_id in to_remove:
                await self._remove_task_internal(task_id)

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old tasks")

    # ==================== Task Lifecycle ====================

    async def create_task(
        self,
        request: CreateBackgroundTaskRequest,
    ) -> BackgroundTask:
        """
        Create a new background task.

        Args:
            request: Background task creation request

        Returns:
            The created BackgroundTask

        Raises:
            RuntimeError: If thread has too many tasks (abuse prevention)
        """
        # Generate short readable ID
        task_id = f"{request.task_type.value[:3]}-{uuid.uuid4().hex[:8]}"

        # Check thread limit (abuse prevention)
        async with self._data_lock:
            thread_tasks = self._thread_index.get(request.thread_id, set())
            if len(thread_tasks) >= self._max_tasks_per_thread:
                # Remove oldest completed task if limit reached
                oldest = None
                for tid in thread_tasks:
                    t = self._tasks.get(tid)
                    if t and t.is_completed:
                        if oldest is None or t.created_at < oldest.created_at:
                            oldest = t
                if oldest:
                    await self._remove_task_internal(oldest.task_id)
                else:
                    raise RuntimeError(
                        f"Thread {request.thread_id} has too many active tasks "
                        f"(max {self._max_tasks_per_thread})"
                    )

        task = BackgroundTask(
            task_id=task_id,
            task_type=request.task_type,
            title=request.title,
            description=request.description,
            tool_name=request.tool_name,
            thread_id=request.thread_id,
            project_id=request.project_id,
            timeout_seconds=request.timeout_seconds,
            metadata=request.metadata or {},
        )

        async with self._data_lock:
            self._tasks[task_id] = task
            self._index_task(task)

        await self._publish_event(task, "created")
        logger.info(f"Task created: {task_id} ({request.title})")

        return task

    async def start_task(self, task_id: str, process_id: int | None = None) -> bool:
        """
        Mark task as started (running).
        
        Args:
            task_id: Task identifier
            process_id: Optional OS process ID for cancellation
            
        Returns:
            True if state changed, False if task not found or already completed
        """
        async with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.is_completed:
                return False

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            if process_id:
                task.process_id = process_id

            self._update_status_index(task_id, TaskStatus.PENDING, TaskStatus.RUNNING)

        await self._publish_event(task, "started")
        return True

    async def complete_task(self, task_id: str, result: Any = None) -> bool:
        """
        Mark task as successfully completed.
        
        Args:
            task_id: Task identifier
            result: Optional result data
            
        Returns:
            True if state changed, False otherwise
        """
        async with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.is_completed:
                return False

            old_status = task.status
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now()

            self._update_status_index(task_id, old_status, TaskStatus.COMPLETED)

        await self._publish_event(task, "completed")
        logger.info(f"Task completed: {task_id}")
        return True

    async def fail_task(self, task_id: str, error: str) -> bool:
        """
        Mark task as failed.
        
        Args:
            task_id: Task identifier
            error: Error message
            
        Returns:
            True if state changed, False otherwise
        """
        async with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.is_completed:
                return False

            old_status = task.status
            task.status = TaskStatus.FAILED
            task.error_message = error
            task.completed_at = datetime.now()

            self._update_status_index(task_id, old_status, TaskStatus.FAILED)

        await self._publish_event(task, "failed")
        logger.warning(f"Task failed: {task_id} - {error}")
        return True

    async def timeout_task(self, task_id: str) -> bool:
        """Mark task as timed out."""
        async with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.is_completed:
                return False

            old_status = task.status
            task.status = TaskStatus.TIMEOUT
            task.completed_at = datetime.now()

            self._update_status_index(task_id, old_status, TaskStatus.TIMEOUT)

        await self._publish_event(task, "timeout")
        logger.warning(f"Task timeout: {task_id}")
        return True

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        This calls the task's cancellation callback if registered.
        
        Returns:
            True if cancelled, False if task not found or already completed
        """
        async with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.is_completed:
                return False

        # Call cancel outside lock to avoid deadlock
        success = await task.cancel()
        if success:
            async with self._data_lock:
                self._update_status_index(task_id, task.status, TaskStatus.CANCELLED)

            await self._publish_event(task, "cancelled")
            logger.info(f"Task cancelled: {task_id}")

        return success

    # ==================== Output Management ====================

    def append_output(self, task_id: str, output: str) -> bool:
        """
        Append output to a task.
        
        This is synchronous (non-async) for performance - 
        called frequently during task execution.
        
        Args:
            task_id: Task identifier
            output: Output line(s) to append
            
        Returns:
            True if appended, False if task not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.append_output(output)

        # Publish output event (fire and forget)
        asyncio.create_task(self._publish_output_event(task, output))

        return True

    # ==================== Query Methods ====================

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_thread_tasks(
        self,
        thread_id: str,
        include_completed: bool = True,
    ) -> list[BackgroundTask]:
        """
        Get all tasks for a thread.
        
        Args:
            thread_id: Thread identifier
            include_completed: If False, filter out completed tasks
            
        Returns:
            List of tasks (sorted by created_at desc)
        """
        task_ids = self._thread_index.get(thread_id, set())
        tasks = [self._tasks[tid] for tid in task_ids if tid in self._tasks]

        if not include_completed:
            tasks = [t for t in tasks if not t.is_completed]

        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def get_active_tasks(self, thread_id: str | None = None) -> list[BackgroundTask]:
        """
        Get all non-completed tasks.
        
        Args:
            thread_id: Optional thread filter
        """
        if thread_id:
            return self.get_thread_tasks(thread_id, include_completed=False)

        active = [t for t in self._tasks.values() if not t.is_completed]
        active.sort(key=lambda t: t.created_at, reverse=True)
        return active

    def get_running_tasks(self, tool_name: str | None = None) -> list[BackgroundTask]:
        """Get currently running tasks."""
        running = [t for t in self._tasks.values() if t.is_running]
        if tool_name:
            running = [t for t in running if t.tool_name == tool_name]
        return running

    # ==================== Internal Methods ====================

    def _index_task(self, task: BackgroundTask) -> None:
        """Add task to indexes."""
        # Thread index
        if task.thread_id not in self._thread_index:
            self._thread_index[task.thread_id] = set()
        self._thread_index[task.thread_id].add(task.task_id)

        # Tool index
        if task.tool_name not in self._tool_index:
            self._tool_index[task.tool_name] = set()
        self._tool_index[task.tool_name].add(task.task_id)

        # Status index
        if task.status not in self._status_index:
            self._status_index[task.status] = set()
        self._status_index[task.status].add(task.task_id)

    def _update_status_index(
        self,
        task_id: str,
        old_status: TaskStatus,
        new_status: TaskStatus,
    ) -> None:
        """Update status index when task status changes."""
        if old_status in self._status_index:
            self._status_index[old_status].discard(task_id)

        if new_status not in self._status_index:
            self._status_index[new_status] = set()
        self._status_index[new_status].add(task_id)

    async def _remove_task_internal(self, task_id: str) -> None:
        """Remove task from all data structures."""
        task = self._tasks.get(task_id)
        if not task:
            return

        # Remove from indexes
        self._thread_index.get(task.thread_id, set()).discard(task_id)
        self._tool_index.get(task.tool_name, set()).discard(task_id)
        self._status_index.get(task.status, set()).discard(task_id)

        # Remove from primary storage
        del self._tasks[task_id]

    # ==================== Event Publishing ====================

    async def _publish_event(self, task: BackgroundTask, event_type: str) -> None:
        """
        Publish task event to notification systems.
        
        This integrates with existing EvoLoop infrastructure:
        - Cache Pub/Sub (for SSE streaming to frontend)
        - Activity Monitor (for logging/auditing)
        """
        event_data = {
            "type": f"task_{event_type}",
            "task": task.to_dict(include_output=False),
            "timestamp": datetime.now().isoformat(),
        }

        # Publish to EventBus for SSE
        from app.core.engine.message.event_bus import get_event_bus
        await get_event_bus().publish(
            f"task:{task.thread_id}:events",
            json.dumps(event_data)
        )

        # Log to activity monitor
        try:
            from app.core.monitoring.activity import activity_monitor
            await activity_monitor.record_task_update(task)
        except Exception as e:
            logger.debug(f"Failed to log to activity monitor: {e}")

    async def _publish_output_event(self, task: BackgroundTask, output: str) -> None:
        """Publish output event (throttled)."""
        # Only publish output events for streaming tasks
        # to avoid flooding the event bus
        if task.metadata.get("enable_streaming_output"):
            try:
                from app.core.engine.message.event_bus import get_event_bus
                await get_event_bus().publish(
                    f"task:{task.thread_id}:output",
                    json.dumps({
                        "task_id": task.task_id,
                        "output": output[-500:],  # Last 500 chars
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass  # Output events are best-effort

    # ==================== Stats ====================

    def get_stats(self) -> BackgroundTaskManagerStats:
        """Get manager statistics."""
        return BackgroundTaskManagerStats(
            total_tasks=len(self._tasks),
            by_status={
                status.value: len(ids)
                for status, ids in self._status_index.items()
            },
            by_thread=len(self._thread_index),
            by_tool={
                tool: len(ids) for tool, ids in self._tool_index.items()
            },
        )
