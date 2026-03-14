"""
Task queue for EvoLoop Client.

Server mode (Celery + Redis) has been moved to the server branch.
Client uses local async execution (no broker, runs in-process).
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class LocalTask:
    """
    Local task implementation for client mode.
    Mimics Celery Task API but runs in-process.
    """

    def __init__(self, func: Callable, name: str = None, bind: bool = False):
        self.func = func
        self.name = name or func.__module__ + "." + func.__name__
        self.bind = bind
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__

    async def run(self, *args, **kwargs):
        """Execute the task immediately (blocking in current thread)."""
        try:
            if self.bind:
                result = await self.func(self, *args, **kwargs)
            else:
                result = await self.func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"[LocalTask] Error in {self.name}: {e}")
            raise

    def apply_async(self, args: tuple = None, kwargs: dict = None, **options) -> Any:
        """Queue task for async execution (client mode: just schedule)."""
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

    async def get(self, timeout: float = None, propagate: bool = True):
        """Execute and return result."""
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


class LocalCelery:
    """
    Mock Celery app for client mode.
    Provides @app.task decorator and basic API.
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

    def send_task(self, name: str, args: tuple = None, kwargs: dict = None, **options) -> LocalAsyncResult:
        """Send a task by name."""
        args = args or ()
        kwargs = kwargs or {}

        if name not in self.tasks:
            try:
                module_path = name.rsplit(".", 1)[0]
                __import__(module_path)
            except Exception as e:
                logger.error(f"[LocalCelery] Failed to import task module {name}: {e}")
                raise ValueError(f"Unknown task: {name}")

        if name not in self.tasks:
            raise ValueError(f"Unknown task: {name}")

        return self.tasks[name].apply_async(args=args, kwargs=kwargs)

    def conf(self):
        """Mock config."""
        return {}

    def start(self, **kwargs):
        logger.info("[LocalCelery] Start called (no-op in client mode)")

    def worker_main(self, **kwargs):
        logger.info("[LocalCelery] Worker main called (no-op in client mode)")


# Client-only: Local task runner
celery_app = LocalCelery("evoloop_local")

# Register some built-in tasks
@celery_app.task
async def cleanup_screenshots(dry_run: bool = False):
    """Placeholder for screenshot cleanup in client mode."""
    logger.info(f"[ClientTask] cleanup_screenshots(dry_run={dry_run})")

@celery_app.task
async def cleanup_screen_recordings(dry_run: bool = False):
    """Placeholder for recording cleanup in client mode."""
    logger.info(f"[ClientTask] cleanup_screen_recordings(dry_run={dry_run})")

logger.info("[Celery] Client mode enabled with local task runner")


# Compatibility: shared_task decorator
def shared_task(func=None, *, name=None, bind=False, **options):
    """
    Compatible shared_task decorator for LocalCelery.

    Usage:
        @shared_task
        async def my_task():
            pass

        @shared_task(name="custom_name", bind=True)
        async def my_task(self):
            pass
    """
    def decorator(f):
        task_name = name or f.__module__ + "." + f.__name__
        task = LocalTask(f, name=task_name, bind=bind)
        celery_app.tasks[task_name] = task
        return task

    if func is not None:
        return decorator(func)
    return decorator


__all__ = ["celery_app", "shared_task"]
