"""
Task Scheduler Abstractions for EvoLoop.

Provides Protocol and ABC definitions for task scheduling implementations.
This allows for both distributed (Celery + Redis) and embedded (Huey + SQLite)
modes to share a common interface.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskResult(Protocol):
    """
    Protocol for task result handles.

    Implementations:
    - celery.result.AsyncResult (full mode)
    - LocalAsyncResult (embedded mode)
    """

    id: str
    """Unique task identifier."""

    async def get(self, timeout: float = None, propagate: bool = True) -> Any:
        """
        Wait for and return the task result.

        Args:
            timeout: Maximum time to wait in seconds
            propagate: If True, re-raise exceptions; if False, return them

        Returns:
            Task return value

        Raises:
            TimeoutError: If timeout is reached
            Exception: Task exception if propagate=True
        """
        ...

    def ready(self) -> bool:
        """Return True if the task has completed (successfully or not)."""
        ...

    def successful(self) -> bool:
        """Return True if the task completed successfully."""
        ...


@runtime_checkable
class Task(Protocol):
    """
    Protocol for task objects.

    Implementations:
    - celery.app.task.Task (full mode)
    - LocalTask (embedded mode)
    """

    name: str
    """Fully qualified task name (e.g., 'app.module.task_name')."""

    def delay(self, *args, **kwargs) -> TaskResult:
        """
        Shortcut for apply_async with star arguments.

        Usage:
            result = my_task.delay(arg1, arg2, kwarg1='value')
        """
        ...

    def apply_async(
        self, args: tuple = None, kwargs: dict = None, **options
    ) -> TaskResult:
        """
        Queue task for asynchronous execution.

        Args:
            args: Positional arguments for the task
            kwargs: Keyword arguments for the task
            **options: Implementation-specific options

        Returns:
            TaskResult handle for monitoring/retrieving result
        """
        ...


class TaskScheduler(ABC):
    """
    Abstract base class for task schedulers.

    Implementations:
    - Celery: Distributed task queue with Redis broker
    - Huey: In-process task queue with SQLite persistence for embedded mode

    Usage:
        scheduler = create_celery_app()  # Returns appropriate implementation

        # Register tasks
        @scheduler.task(name="my_task")
        async def my_task(x, y):
            return x + y

        # Send tasks
        result = scheduler.send_task("my_task", args=(1, 2))
        value = await result.get()
    """

    @abstractmethod
    def send_task(self, name: str, args: tuple = None, kwargs: dict = None, **options) -> TaskResult:
        """
        Send a task by name to the queue.

        Args:
            name: Fully qualified task name
            args: Positional arguments
            kwargs: Keyword arguments
            **options: Implementation-specific options

        Returns:
            TaskResult handle

        Raises:
            ValueError: If task name is unknown
        """
        pass

    @abstractmethod
    def task(self, func: Callable = None, *, name: str = None, bind: bool = False, **options) -> Task:
        """
        Decorator to register a function as a task.

        Args:
            func: Function to register (when used as @app.task)
            name: Override the task name (default: module.function)
            bind: If True, first argument is the task instance (self)
            **options: Implementation-specific options

        Returns:
            Task wrapper that can be called directly or queued
        """
        pass

    @abstractmethod
    def start(self, **kwargs) -> None:
        """
        Start the scheduler/worker.

        For Celery: Start the worker process
        For Huey: Start the consumer
        """
        pass

    @abstractmethod
    def worker_main(self, **kwargs) -> None:
        """
        Run as a worker process.

        For Celery: Start consuming tasks
        For Huey: Start the consumer
        """
        pass
