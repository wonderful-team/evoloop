"""
Task Queue Factory for EvoLoop.

Switches between Celery (full mode) and Huey (embedded mode)
based on ``EMBEDDED_MODE`` setting.

Usage:
    from app.infrastructure.queue.factory import get_scheduler

    scheduler = get_scheduler()

    @scheduler.task(name="my_task")
    async def my_task(x, y):
        return x + y

    result = scheduler.send_task("my_task", args=(1, 2))
    value = await result.get(timeout=30)
"""

import asyncio
import functools
import logging

from app.core.config import settings
from app.infrastructure.queue.base import TaskScheduler

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: TaskScheduler | None = None


def create_task_scheduler() -> TaskScheduler:
    """
    Create appropriate task scheduler based on EMBEDDED_MODE.

    Returns:
        TaskScheduler instance
    """
    global _scheduler

    if settings.EMBEDDED_MODE:
        from app.infrastructure.queue.huey_queue import HueyTaskScheduler

        _scheduler = HueyTaskScheduler()
        logger.info("[QueueFactory] Created Huey scheduler (embedded mode)")
    else:
        from app.infrastructure.queue.celery_app import create_celery_app

        _scheduler = create_celery_app()
        logger.info("[QueueFactory] Created Celery scheduler (full mode)")

    return _scheduler


def get_scheduler() -> TaskScheduler:
    """
    Get global scheduler instance (singleton).

    Creates scheduler on first call based on EMBEDDED_MODE.

    Returns:
        TaskScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = create_task_scheduler()
    return _scheduler


def reset_scheduler():
    """Reset global scheduler (for testing)."""
    global _scheduler
    _scheduler = None
    logger.debug("[QueueFactory] Scheduler reset")


# Convenience function for task registration
def shared_task(
    func=None,
    *,
    name: str = None,
    bind: bool = False,
    retries: int = 0,
    retry_delay: int = 0,
    **options,
):
    """
    Universal shared_task decorator.

    Works with any scheduler (Celery/Huey).

    Args:
        func: Function to decorate
        name: Task name
        bind: If True, pass task instance as first argument
        retries: Number of retries on failure
        retry_delay: Delay between retries in seconds
        **options: Additional scheduler-specific options

    Returns:
        Decorated task function

    Example:
        @shared_task(name="my_task", retries=3, retry_delay=60)
        async def my_task(x, y):
            return x + y

        # Dispatch
        result = my_task.delay(1, 2)
        value = await result.get(timeout=30)
    """
    scheduler = get_scheduler()

    def decorator(f):
        target_f = f

        # If the scheduler is real Celery and the function is async, wrap it.
        # HueyTaskScheduler handles async natively, so we only wrap for real Celery.
        if asyncio.iscoroutinefunction(f) and type(scheduler).__name__ == "Celery":

            @functools.wraps(f)
            def _celery_async_wrapper(*args, **kwargs):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                async def _execute():
                    from app.infrastructure.database.resource_manager import (
                        db_resource_manager,
                    )
                    await db_resource_manager.initialize(create_tables=False, seed_data=False)
                    return await f(*args, **kwargs)

                try:
                    return loop.run_until_complete(_execute())
                finally:
                    try:
                        from app.utils.async_utils import flush_loop_bound_resources

                        loop.run_until_complete(flush_loop_bound_resources())
                    except Exception as e:
                        logger.warning(f"[Task] Failed to flush resources in task {f.__name__}: {e}", exc_info=True)

            target_f = _celery_async_wrapper

        return scheduler.task(
            target_f,
            name=name,
            bind=bind,
            retries=retries,
            retry_delay=retry_delay,
            **options,
        )

    if func is not None:
        return decorator(func)
    return decorator


# Periodic task decorator
def periodic_task(cron: str, name: str = None, **kwargs):
    """
    Decorator for periodic tasks.

    Args:
        cron: Cron expression (e.g., '0 * * * *' for hourly)
        name: Task name
        **kwargs: Additional options

    Example:
        @periodic_task(cron='0 2 * * *')  # Daily at 2 AM
        async def cleanup_task():
            pass
    """
    scheduler = get_scheduler()

    # Check if scheduler supports periodic tasks
    if hasattr(scheduler, "periodic_task"):
        return scheduler.periodic_task(cron, name=name, **kwargs)
    else:
        logger.warning(
            f"[QueueFactory] Scheduler {type(scheduler).__name__} "
            "does not support periodic tasks"
        )

        # Return no-op decorator
        def decorator(f):
            return f

        return decorator


# Backward compatibility
create_celery_app = create_task_scheduler  # Alias for old code
