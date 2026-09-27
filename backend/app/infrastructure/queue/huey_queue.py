"""
Huey Task Queue Implementation for EvoLoop (Embedded Mode).

In-process task queue with SQLite persistence for embedded mode
without external dependencies like Redis.

Features:
- Task persistence via SQLite
- Automatic retries with exponential backoff
- Periodic/scheduled tasks
- Task result storage
- Compatible with Celery-style API
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

# Lazy import huey to avoid import errors if not installed
try:
    from huey import Huey, SqliteHuey
    from huey.api import Task

    HUEY_AVAILABLE = True
except ImportError:
    HUEY_AVAILABLE = False
    SqliteHuey = None
    Huey = None
    Task = None


from app.infrastructure.queue.base import SyncTaskMixin, TaskResult, TaskScheduler

logger = logging.getLogger(__name__)


class HueyTaskResult(TaskResult):
    """
    Task result wrapper for Huey tasks.
    Compatible with Celery AsyncResult interface.
    """

    def __init__(self, huey_task: Task, huey_instance: Huey):
        self._task = huey_task
        self._huey = huey_instance
        self.id = huey_task.id

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
        start_time = time.time()
        check_interval = 0.1  # Check every 100ms

        while True:
            result = self._huey.result(self.id, preserve=True)

            if result is not None:
                # Task completed
                if isinstance(result, Exception):
                    if propagate:
                        raise result
                    return result
                return result

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(f"Task {self.id} timed out after {timeout}s")

            await asyncio.sleep(check_interval)

    def ready(self) -> bool:
        """Return True if the task has completed."""
        result = self._huey.result(self.id, preserve=True)
        return result is not None

    def successful(self) -> bool:
        """Return True if the task completed successfully."""
        result = self._huey.result(self.id, preserve=True)
        if result is None:
            return False
        return not isinstance(result, Exception)


class HueyTaskScheduler(TaskScheduler, SyncTaskMixin):
    """
    Huey-based task scheduler for embedded mode.

    Provides Celery-compatible API using Huey + SQLite as backend.
    Supports:
    - Task persistence
    - Automatic retries
    - Delayed execution
    - Periodic tasks (via Huey consumer)
    """

    def __init__(self, name: str = "evoloop_huey"):
        if not HUEY_AVAILABLE:
            raise ImportError(
                "Huey is not installed. Install with: pip install huey[sqlite]"
            )

        self.name = name
        self._huey: SqliteHuey | None = None
        self._tasks: dict[str, Callable] = {}
        self._periodic_tasks: dict[str, Callable] = {}
        self._init_huey()

    def _init_huey(self):
        """Initialize Huey with SQLite storage."""
        # Use managed path from DatabaseResourceManager
        from app.infrastructure.database.resource_manager import db_resource_manager

        db_path = db_resource_manager.task_queue_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._huey = SqliteHuey(
            name=self.name,
            filename=str(db_path),
            # Immediate mode for better concurrency
            immediate=False,
            # Store results
            results=True,
            # Result expiration (7 days)
            store_none=False,
            # Busy timeout 30s to avoid "database is locked" with multi-process workers
            timeout=30,
            # Allow connections from multiple threads within the same process
            check_same_thread=False,
        )

        # Critical: SqliteStorage defaults to 'begin exclusive', which causes
        # "database is locked" errors when multiple processes/threads contend.
        # In WAL mode, 'begin immediate' only blocks other writers (not readers),
        # dramatically reducing lock contention in multi-process deployments.
        self._huey.storage.begin_sql = "begin immediate"

        logger.info(
            f"[Huey] Initialized with SQLite at {db_path} via ResourceManager (begin=immediate, timeout=30s)"
        )

    def task(
        self,
        func: Callable = None,
        *,
        name: str = None,
        bind: bool = False,
        retries: int = 0,
        retry_delay: int = 0,
        **options,
    ) -> Callable:
        """
        Decorator to register a function as a task.

        Args:
            func: Function to register
            name: Override task name
            bind: If True, first argument is task instance (self)
            retries: Number of retries on failure
            retry_delay: Delay between retries in seconds
            **options: Additional options

        Returns:
            Task wrapper
        """

        def decorator(f: Callable) -> Callable:
            task_name = name or f"{f.__module__}.{f.__name__}"

            # Idempotent registration: tests and hot-reloads may re-import the
            # same module, causing Huey's registry to raise a duplicate-name
            # error. Return the existing wrapper instead of crashing.
            if task_name in self._tasks:
                logger.debug(f"[Huey] Task already registered, returning existing wrapper: {task_name}")
                return self._tasks[task_name]["func"]

            # Define wrapper with correct module/name BEFORE Huey registration.
            # Huey's Registry uses func.__module__ to build the task registry key,
            # so we must set it before @self._huey.task() reads it.
            def _huey_wrapper(*args, **kwargs):
                # Handle async functions
                if asyncio.iscoroutinefunction(f):
                    return self._run_async_task(f, bind, *args, **kwargs)
                else:
                    # Sync function
                    if bind:
                        return f(None, *args, **kwargs)
                    return f(*args, **kwargs)

            _huey_wrapper.__name__ = f.__name__
            _huey_wrapper.__module__ = f.__module__
            _huey_wrapper.__doc__ = f.__doc__

            # Register with Huey — now __module__ is correct
            huey_wrapper = self._huey.task(
                name=task_name,
                retries=retries,
                retry_delay=retry_delay,
            )(_huey_wrapper)

            # Store task info with the Huey-wrapped function
            # This is crucial for send_task to find the registered task
            self._tasks[task_name] = {
                "func": huey_wrapper,  # Store huey_wrapper, not f!
                "name": task_name,
                "bind": bind,
                "retries": retries,
                "retry_delay": retry_delay,
            }

            # Also store on the original function for discovery
            f._huey_task_name = task_name
            f._huey_wrapper = huey_wrapper

            # Add Celery-compatible methods
            huey_wrapper.delay = lambda *a, **kw: self._create_result(
                huey_wrapper(*a, **kw)
            )
            huey_wrapper.apply_async = lambda args=None, kwargs=None: (
                self._create_result(huey_wrapper(*(args or ()), **(kwargs or {})))
            )

            huey_wrapper.__name__ = f.__name__
            huey_wrapper.__module__ = f.__module__  # Critical: preserve original module
            huey_wrapper.__doc__ = f.__doc__
            huey_wrapper.name = task_name

            logger.debug(f"[Huey] Registered task: {task_name}")
            return huey_wrapper

        if func is not None:
            return decorator(func)
        return decorator

    def _run_async_task(self, func: Callable, bind: bool, *args, **kwargs):
        """Run async function in Huey worker with enhanced error handling.

        Event loop strategy: reuse the thread's existing loop if one is set
        (set_event_loop by worker startup / a previous task), instead of
        creating a fresh loop per task. Per-task loops caused cross-loop usage
        of loop-bound resources (MCP sessions, evocloud clients) which hung on
        health checks (AsyncExitStack bound to a different task/loop).
        """
        import traceback

        # Reuse the thread's event loop when one is already set (persistent
        # loop from worker startup), otherwise create and set one.
        try:
            loop = asyncio.get_running_loop()
            is_running = True
        except RuntimeError:
            is_running = False
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

        # Helper to execute the core logic
        async def _execute():
            from app.infrastructure.database.resource_manager import db_resource_manager

            await db_resource_manager.initialize(create_tables=False)
            if bind:
                return await func(None, *args, **kwargs)
            else:
                return await func(*args, **kwargs)

        try:
            if is_running:
                # We can't use run_until_complete here.
                # If we are in immediate mode, we might need a separate thread or a different approach.
                # However, for Huey tasks triggered via send_task in a running loop,
                # we actually want to schedule it.
                # BUT Huey's immediate mode expects a return value NOW.

                # Use a helper to run coroutine in a thread-safe way if needed,
                # or just use a nested loop strategy (like nest_asyncio).
                import nest_asyncio

                nest_asyncio.apply(loop)
                return loop.run_until_complete(_execute())
            if loop.is_running():
                # worker：事件循环由 bin/run_worker.py 的后台线程 run_forever 持续驱动。
                # 用线程安全投递 + 阻塞等结果；不能 run_until_complete（loop 已在跑）。
                future = asyncio.run_coroutine_threadsafe(_execute(), loop)
                return future.result()
            return loop.run_until_complete(_execute())
        except Exception as e:
            # Log the full exception for debugging
            error_msg = f"[Huey] Task execution failed: {func.__name__}: {type(e).__name__}: {e}"
            logger.error(error_msg)
            logger.exception(f"[Huey] Full traceback:\n{traceback.format_exc()}")
            # Re-raise to let Huey handle retries
            raise
        finally:
            # Do NOT flush loop-bound resources here: with a persistent/reused
            # loop, flushing would tear down MCP/evocloud sessions that the
            # next task relies on (causing reconnect churn or cross-loop hangs).
            pass

    def _create_result(self, huey_task: Task) -> HueyTaskResult:
        """Create a result wrapper for a Huey task."""
        return HueyTaskResult(huey_task, self._huey)

    def send_task(
        self,
        name: str,
        args: tuple = None,
        kwargs: dict = None,
        _retry_count: int = 0,
        **options,
    ) -> HueyTaskResult:
        """
        Send a task by name.

        Args:
            name: Fully qualified task name
            args: Positional arguments
            kwargs: Keyword arguments
            _retry_count: Internal retry counter (do not use)
            **options: Additional options

        Returns:
            TaskResult handle

        Raises:
            ValueError: If task name is unknown or max retries exceeded
        """
        args = args or ()
        kwargs = kwargs or {}

        # Load task if not already loaded
        if name not in self._tasks:
            self._load_task_module(name)

        if name not in self._tasks:
            raise ValueError(f"Unknown task: {name}")

        task_info = self._tasks[name]
        huey_wrapper = task_info["func"]  # This is the Huey-wrapped function

        # Execute the task directly using the stored Huey wrapper
        # The huey_wrapper is already registered with Huey via @self._huey.task()
        try:
            # huey_wrapper when called will enqueue the task via Huey
            huey_task = huey_wrapper(*args, **kwargs)
            logger.debug(f"[Huey] Task {name} dispatched via stored wrapper")
            return self._create_result(huey_task)

        except Exception as e:
            # If execution fails, log and re-raise
            logger.exception(f"[Huey] Task {name} execution failed: {e}")
            raise

    def _load_task_module(self, task_name: str) -> bool:
        """Load task module dynamically by importing every known task module."""
        from app.infrastructure.queue.discovery import discover_task_modules

        for module_path in discover_task_modules():
            try:
                __import__(module_path)
            except Exception:
                logger.warning(
                    "[Huey] Failed to import task module %s", module_path, exc_info=True
                )
                continue
            # Check if the task name is now registered
            if task_name in self._tasks:
                logger.debug(f"[Huey] Loaded module for {task_name}: {module_path}")
                return True
        return False

    def start(self, **kwargs):
        """Start the Huey consumer."""
        logger.info("[Huey] Starting consumer...")
        # In embedded mode, consumer is started separately
        # This method is mainly for API compatibility
        pass

    def worker_main(self, **kwargs):
        """Run as worker process."""
        logger.info("[Huey] Starting worker main...")

        # Pre-load all task modules to ensure tasks are registered
        self._preload_task_modules()

        # Start the Huey consumer
        from huey.consumer import Consumer

        # Disable signal handling for thread safety (non-main thread)
        # Use simple worker type to avoid signal issues
        consumer_kwargs = {
            "workers": kwargs.get("workers", 2),
            "worker_type": kwargs.get("worker_type", "thread"),
            "initial_delay": kwargs.get("initial_delay", 0.1),
            "max_delay": kwargs.get("max_delay", 10),
            "backoff": kwargs.get("backoff", 1.15),
            "scheduler_interval": kwargs.get("scheduler_interval", 1),
            "periodic": kwargs.get("periodic", True),
            "check_worker_health": kwargs.get("check_worker_health", True),
            "health_check_interval": kwargs.get("health_check_interval", 10),
        }

        consumer = Consumer(self._huey, **consumer_kwargs)

        # Override signal handling to avoid errors in non-main thread
        consumer._set_signal_handlers = lambda: None  # Disable signal handlers

        consumer.run()

    def _preload_task_modules(self):
        """Pre-load all task modules to register tasks in worker process."""
        from app.infrastructure.queue.discovery import discover_task_modules

        logger.info("[Huey] Pre-loading task modules...")
        task_modules = discover_task_modules()
        loaded_count = 0

        for module_path in task_modules:
            try:
                __import__(module_path)
                loaded_count += 1
                logger.debug(f"[Huey] Loaded module: {module_path}")
            except Exception as e:
                logger.warning(f"[Huey] Failed to load {module_path}: {e}", exc_info=True)

        logger.info(f"[Huey] Pre-loaded {loaded_count} task modules")

    def get_huey(self) -> SqliteHuey:
        """Get the underlying Huey instance."""
        return self._huey

    def periodic_task(self, cron: str, name: str = None, **kwargs):
        """
        Decorator for periodic tasks.

        Args:
            cron: Cron expression (e.g., '0 * * * *' for hourly)
            name: Task name
            **kwargs: Additional options
        """
        from huey import crontab

        # huey 的 crontab() 期待 5 个位置参数（minute hour day month dow），
        # 不是单个 cron 字符串。拆解字符串避免整个串被当成 minute 导致永不匹配。
        fields = cron.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {cron!r} (expected 5 fields)")
        minute, hour, day, month, day_of_week = fields

        def decorator(f: Callable):
            task_name = name or f"{f.__module__}.{f.__name__}"

            # Idempotent registration for periodic tasks as well.
            if task_name in self._periodic_tasks:
                logger.debug(f"[Huey] Periodic task already registered, returning existing wrapper: {task_name}")
                return self._periodic_tasks[task_name]

            @self._huey.periodic_task(
                crontab(minute, hour, day, month, day_of_week), name=task_name, **kwargs
            )
            def periodic_wrapper():
                if asyncio.iscoroutinefunction(f):
                    return self._run_async_task(f, False)
                return f()

            periodic_wrapper.__name__ = f.__name__
            periodic_wrapper.__doc__ = f.__doc__
            self._periodic_tasks[task_name] = periodic_wrapper
            return periodic_wrapper

        return decorator


def get_huey_scheduler() -> HueyTaskScheduler:
    """Get or create global Huey scheduler instance.

    Uses factory.get_scheduler() to ensure single instance across the app.
    """
    from app.infrastructure.queue.factory import get_scheduler

    scheduler = get_scheduler()
    if not isinstance(scheduler, HueyTaskScheduler):
        raise RuntimeError(f"Expected HueyTaskScheduler, got {type(scheduler).__name__}")
    return scheduler


# Compatibility: shared_task decorator
def shared_task(
    func: Callable = None,
    *,
    name: str = None,
    bind: bool = False,
    retries: int = 0,
    retry_delay: int = 0,
    **options,
):
    """
    Compatible shared_task decorator for Huey.
    Works with both Celery and Huey.
    """
    scheduler = get_huey_scheduler()

    def decorator(f):
        return scheduler.task(
            f,
            name=name,
            bind=bind,
            retries=retries,
            retry_delay=retry_delay,
            **options
        )

    if func is not None:
        return decorator(func)
    return decorator
