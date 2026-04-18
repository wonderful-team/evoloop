"""
Task queue for EvoLoop Backend.

DEPRECATED: Use app.infrastructure.queue.factory instead.

This module is kept for backward compatibility.
New code should use:
    from app.infrastructure.queue.factory import get_scheduler, shared_task

Supports two modes:
- Full mode: Celery + Redis (traditional)
- Embedded mode: LocalCelery (in-process, no broker) - DEPRECATED, use Huey instead

Both implementations conform to the TaskScheduler abstract base class.
"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.config import settings
from app.infrastructure.queue.base import TaskScheduler, SyncTaskMixin
from app.infrastructure.queue.registry import TASK_MODULE_MAP

logger = logging.getLogger(__name__)


# Temporary registry for tasks registered before celery_app is created
_pending_shared_tasks: list[tuple] = []


# =============================================================================
# LocalCelery Implementation (for Embedded Mode)
# =============================================================================

class LocalTask:
    """
    Local task implementation for embedded mode.
    Mimics Celery Task API but runs in-process.
    """

    def __init__(self, func: Callable, name: str = None, bind: bool = False):
        self.func = func
        self.name = name or func.__module__ + "." + func.__name__
        self.bind = bind
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__

    async def run(self, *args, **kwargs):
        """Execute the task immediately."""
        try:
            if self.bind:
                if asyncio.iscoroutinefunction(self.func):
                    result = await self.func(self, *args, **kwargs)
                else:
                    # Sync function - run in thread pool to avoid blocking
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, functools.partial(self.func, self, *args, **kwargs))
            else:
                if asyncio.iscoroutinefunction(self.func):
                    result = await self.func(*args, **kwargs)
                else:
                    # Sync function - run in thread pool to avoid blocking
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, functools.partial(self.func, *args, **kwargs))
            return result
        except Exception as e:
            logger.error(f"[LocalTask] Error in {self.name}: {e}")
            raise

    def apply_async(self, args: tuple = None, kwargs: dict = None, **options) -> Any:
        """Queue task for async execution (embedded mode: just schedule)."""
        args = args or ()
        kwargs = kwargs or {}
        return LocalAsyncResult(self, args, kwargs)

    def delay(self, *args, **kwargs) -> Any:
        """Shortcut for apply_async."""
        return self.apply_async(args=args, kwargs=kwargs)

    def __call__(self, *args, **kwargs):
        """Allow direct calling of the task."""
        if asyncio.iscoroutinefunction(self.func):
            return self.run(*args, **kwargs)
        else:
            return self.func(*args, **kwargs)


class LocalAsyncResult:
    """Mock Celery AsyncResult for local tasks."""

    def __init__(self, task: LocalTask, args: tuple, kwargs: dict):
        self.task = task
        self.args = args
        self.kwargs = kwargs
        self._result = None
        self._ready = False
        self._exception = None
        # Generate a unique ID for compatibility with Celery AsyncResult
        import uuid
        self.id = str(uuid.uuid4())
        # Immediately schedule the task in background (embedded mode: fire and forget)
        self._schedule_task()

    def _schedule_task(self):
        """Schedule the task to run in the background event loop."""
        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
            # Schedule the task as a background job
            self._async_task = loop.create_task(self._run_task())
        except RuntimeError:
            # No event loop running, log warning - task won't execute
            logger.warning(f"[LocalAsyncResult] No event loop running, task {self.task.name} may not execute")

    async def _run_task(self):
        """Internal method to execute the task."""
        try:
            self._result = await self.task.run(*self.args, **self.kwargs)
            self._ready = True
        except Exception as e:
            self._exception = e
            self._ready = True
            logger.error(f"[LocalAsyncResult] Task {self.task.name} failed: {e}")

    async def get(self, timeout: float = None, propagate: bool = True):
        """Wait for result and return."""
        if not self._ready:
            # 1. If background task is already running, wait for it
            if hasattr(self, "_async_task") and not self._async_task.done():
                try:
                    if timeout:
                        await asyncio.wait_for(asyncio.shield(self._async_task), timeout=timeout)
                    else:
                        await self._async_task
                except (asyncio.TimeoutError, TimeoutError):
                    raise TimeoutError(f"Task {self.task.name} timed out after {timeout}s")
                except Exception:
                    # _run_task already handles exceptions and sets _exception/_ready
                    pass
            
            # 2. If still not ready (no task was scheduled or it failed silently), run it now
            if not self._ready:
                try:
                    self._result = await self.task.run(*self.args, **self.kwargs)
                    self._ready = True
                except Exception as e:
                    self._exception = e
                    self._ready = True
                    if propagate:
                        raise

        if self._exception and propagate:
            raise self._exception

        return self._result

    def ready(self) -> bool:
        return self._ready

    def successful(self) -> bool:
        return self._ready and self._exception is None


class LocalCelery(TaskScheduler, SyncTaskMixin):
    """
    Embedded mode task scheduler.
    
    Implements TaskScheduler interface using in-process async execution.
    Tasks run in the same event loop, making this suitable for standalone
    deployments without Redis/Celery infrastructure.
    
    Note: By default, tasks are fire-and-forget. For critical operations,
    use execute_sync() or await result.get() to ensure completion.
    """

    def __init__(self, name: str = "evoloop_local"):
        self.name = name
        self.tasks: dict[str, LocalTask] = {}

    def task(self, func: Callable = None, *, bind: bool = False, name: str = None, **options):
        """Decorator to register a task."""
        def decorator(f: Callable) -> LocalTask:
            task_name = name or f.__module__ + "." + f.__name__
            task = LocalTask(f, name=task_name, bind=bind)
            self.tasks[task_name] = task
            logger.debug(f"[LocalCelery] Registered task: {task_name}")
            return task

        if func is not None:
            return decorator(func)
        return decorator

    def _load_task_module(self, task_name: str) -> bool:
        """Load the module containing a specific task. Returns True if loaded."""
        # Check if we have a mapping for this task
        if task_name in TASK_MODULE_MAP:
            module_path = TASK_MODULE_MAP[task_name]
            try:
                __import__(module_path)
                logger.debug(f"[LocalCelery] Loaded module for {task_name}: {module_path}")
                return True
            except Exception as e:
                logger.warning(f"[LocalCelery] Failed to load {module_path}: {e}")
                return False

        # Try to infer module from task name (for tasks like app.module.func)
        if "." in task_name:
            parts = task_name.rsplit(".", 1)
            if len(parts) == 2:
                module_path, func_name = parts
                # Handle both 'app.module.func' and 'app.module.tasks.func'
                try:
                    __import__(module_path)
                    logger.debug(f"[LocalCelery] Loaded module: {module_path}")
                    return True
                except Exception:
                    pass
        return False

    def send_task(self, name: str, args: tuple = None, kwargs: dict = None, **options) -> LocalAsyncResult:
        """Send a task by name."""
        args = args or ()
        kwargs = kwargs or {}

        # Load the task module if not already loaded
        if name not in self.tasks:
            loaded = self._load_task_module(name)
            if not loaded:
                logger.error(f"[LocalCelery] Unknown task: {name}")
                raise ValueError(f"Unknown task: {name}")

        if name not in self.tasks:
            raise ValueError(f"Unknown task: {name}")

        return self.tasks[name].apply_async(args=args, kwargs=kwargs)

    def conf(self):
        """Mock config."""
        return {}

    def start(self, **kwargs):
        logger.info("[LocalCelery] Start called (no-op in embedded mode)")

    def worker_main(self, **kwargs):
        logger.info("[LocalCelery] Worker main called (no-op in embedded mode)")


# Compatibility: shared_task decorator
def shared_task(func=None, *, name=None, bind=False, **options):
    """
    Compatible shared_task decorator for LocalCelery.
    Works with both Celery and LocalCelery.
    """
    def decorator(f):
        task_name = name or f.__module__ + "." + f.__name__
        task = LocalTask(f, name=task_name, bind=bind)
        # Register with the local celery app if it exists, otherwise queue it
        global _celery_app
        if _celery_app and isinstance(_celery_app, LocalCelery):
            _celery_app.tasks[task_name] = task
            logger.debug(f"[shared_task] Registered: {task_name}")
        else:
            # Queue for later registration
            _pending_shared_tasks.append((task_name, task))
            logger.debug(f"[shared_task] Queued for registration: {task_name}")
        return task

    if func is not None:
        return decorator(func)
    return decorator


# =============================================================================
# Celery / LocalCelery Factory
# =============================================================================

def _register_local_tasks(app: LocalCelery):
    """Manually register all task functions for Embedded Mode.

    This is needed because task modules use 'from celery import shared_task'
    which doesn't automatically register with our LocalCelery.
    """
    # First, process any tasks that were queued before celery_app was created
    global _pending_shared_tasks
    for task_name, task in _pending_shared_tasks:
        if task_name not in app.tasks:
            app.tasks[task_name] = task
            logger.debug(f"[LocalCelery] Registered from queue: {task_name}")
    logger.info(f"[LocalCelery] Registered {len(_pending_shared_tasks)} tasks from shared_task queue")
    _pending_shared_tasks = []  # Clear the queue

    # Import task functions and wrap them as LocalTasks
    # Use importlib to avoid circular imports
    import importlib

    try:
        # Engine tasks - dynamically import to avoid circular imports
        engine_tasks = importlib.import_module('app.core.engine.tasks')

        tasks_to_register = [
            ("engine_persist_file_operation", getattr(engine_tasks, 'persist_file_operation_task', None), False),
            ("engine_upload_cloud_log", getattr(engine_tasks, 'upload_cloud_log_task', None), False),
            ("engine_snapshot_steps", getattr(engine_tasks, 'snapshot_steps_task', None), False),
            ("engine_harvest_concepts", getattr(engine_tasks, 'harvest_concepts_task', None), False),
            ("engine_record_episode", getattr(engine_tasks, 'record_episode_task', None), False),
            ("engine_prune_checkpoints", getattr(engine_tasks, 'prune_checkpoints_task', None), False),
            ("engine_persist_message", getattr(engine_tasks, 'persist_message_task', None), False),
            ("engine_cleanup_artifacts", getattr(engine_tasks, 'cleanup_artifacts_task', None), False),
            ("engine_git_harvest", getattr(engine_tasks, 'git_harvest_task', None), False),
            ("engine_reconcile_skill_macro", getattr(engine_tasks, 'reconcile_skill_macro_task', None), False),
            ("engine_scheduler_tick", getattr(engine_tasks, 'engine_scheduler_tick', None), False),
            ("run_autonomous_task_execution", getattr(engine_tasks, 'run_autonomous_task_execution', None), False),
        ]

        registered_count = 0
        for name, func, bind in tasks_to_register:
            if func is not None and name not in app.tasks:
                app.tasks[name] = LocalTask(func, name=name, bind=bind)
                logger.debug(f"[LocalCelery] Registered: {name}")
                registered_count += 1

        logger.info(f"[LocalCelery] Registered {registered_count} engine tasks")

    except Exception as e:
        logger.warning(f"[LocalCelery] Failed to register engine tasks: {e}")

    try:
        # Vision cleanup tasks - dynamically import to avoid circular imports
        vision_cleanup = importlib.import_module('app.core.vision.cleanup')

        vision_tasks = [
            ("cleanup_screenshots", getattr(vision_cleanup, 'cleanup_screenshots', None)),
            ("cleanup_screen_recordings", getattr(vision_cleanup, 'cleanup_screen_recordings', None)),
        ]

        for name, func in vision_tasks:
            if func is not None and name not in app.tasks:
                app.tasks[name] = LocalTask(func, name=name, bind=False)

        logger.info("[LocalCelery] Registered vision cleanup tasks")
    except Exception as e:
        logger.warning(f"[LocalCelery] Failed to register vision tasks: {e}")


def create_celery_app() -> TaskScheduler:
    """
    Create task scheduler based on configuration.
    
    Returns:
        LocalCelery if EMBEDDED_MODE=True, otherwise Celery
    """
    if settings.EMBEDDED_MODE:
        logger.info("[Celery] Embedded mode enabled with LocalCelery (in-process tasks)")
        app = LocalCelery("evoloop_embedded")
        _register_local_tasks(app)
        return app

    # Ensure database directory exists for Celery beat schedule
    db_dir = Path.home() / ".evoloop" / "database"
    db_dir.mkdir(parents=True, exist_ok=True)

    from celery import Celery as RealCelery
    app = RealCelery(
        "evoloop_worker",
        broker=settings.REDIS_URL or "redis://localhost:6379/0",
        backend=settings.REDIS_URL or "redis://localhost:6379/0",
        include=[
            "app.domain.codebase.indexing.tasks",
            "app.domain.project.summarizer",
            "app.domain.project.sync_tasks",
            "app.domain.wiki.tasks",
            "app.core.engine.tasks",
            "app.core.atlas.tasks",
            "app.core.vision.cleanup",
            "app.core.memory.maintenance",
        ],
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        beat_schedule_filename=str(db_dir / "celerybeat-schedule.db"),
        beat_schedule={
            "cleanup-screenshots-daily": {
                "task": "app.core.vision.cleanup_screenshots",
                "schedule": 86400.0,
                "args": (False,),
            },
            "cleanup-screen-recordings-daily": {
                "task": "app.core.vision.cleanup_screen_recordings",
                "schedule": 86400.0,
                "args": (False,),
            },
            "autonomous-scheduler-tick": {
                "task": "engine_scheduler_tick",
                "schedule": 60.0,
            },
        },
    )

    logger.info("[Celery] Full mode enabled with Redis broker")
    return app


# Global Celery/LocalCelery instance
_celery_app: Optional[TaskScheduler] = None


def get_celery_app() -> TaskScheduler:
    """Get or create global legacy celery instance."""
    global _celery_app
    if _celery_app is None:
        _celery_app = create_celery_app()
    return _celery_app
