"""
Task Queue Factory for EvoLoop.

Provides unified interface to switch between:
- Full Mode: Celery + Redis (distributed)
- Embedded Mode: Huey + SQLite (standalone)
- Legacy Mode: LocalCelery (in-memory, deprecated)

Usage:
    from app.infrastructure.queue.factory import create_task_scheduler, get_scheduler
    
    # Get appropriate scheduler based on configuration
    scheduler = get_scheduler()
    
    # Register tasks
    @scheduler.task(name="my_task")
    async def my_task(x, y):
        return x + y
    
    # Dispatch tasks
    result = scheduler.send_task("my_task", args=(1, 2))
    value = await result.get(timeout=30)
"""

import logging
from typing import Optional, Literal

from app.core.config import settings
from app.infrastructure.queue.base import TaskScheduler

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[TaskScheduler] = None


def create_task_scheduler(
    mode: Literal["celery", "huey", "local", "auto"] = "auto"
) -> TaskScheduler:
    """
    Create appropriate task scheduler based on mode.
    
    Args:
        mode: Scheduler mode
            - "celery": Full Celery with Redis
            - "huey": Huey with SQLite (recommended for embedded)
            - "local": LocalCelery (in-memory, deprecated)
            - "auto": Auto-detect based on configuration
            
    Returns:
        TaskScheduler instance
        
    Raises:
        ImportError: If required dependencies are not installed
        ValueError: If invalid mode specified
    """
    global _scheduler
    
    if mode == "auto":
        # Auto-detect based on configuration
        if settings.EMBEDDED_MODE:
            mode = "huey"  # Default to Huey for embedded mode
        else:
            mode = "celery"  # Use Celery for full mode
    
    logger.info(f"[QueueFactory] Creating scheduler: mode={mode}")
    
    if mode == "celery":
        # Full Celery mode with Redis
        try:
            from app.infrastructure.queue.celery import create_celery_app
            _scheduler = create_celery_app()
            logger.info("[QueueFactory] Created Celery scheduler")
        except Exception as e:
            logger.error(f"[QueueFactory] Failed to create Celery scheduler: {e}")
            logger.warning("[QueueFactory] Falling back to Huey scheduler")
            mode = "huey"
    
    if mode == "huey":
        # Huey mode with SQLite
        try:
            from app.infrastructure.queue.huey_queue import HueyTaskScheduler
            _scheduler = HueyTaskScheduler()
            logger.info("[QueueFactory] Created Huey scheduler")
        except ImportError as e:
            logger.error(f"[QueueFactory] Huey not installed: {e}")
            logger.error("Install with: pip install huey[sqlite]")
            raise
        except Exception as e:
            logger.error(f"[QueueFactory] Failed to create Huey scheduler: {e}")
            logger.warning("[QueueFactory] Falling back to LocalCelery")
            mode = "local"
    
    if mode == "local":
        # Legacy LocalCelery mode (in-memory, deprecated)
        try:
            from app.infrastructure.queue.celery import LocalCelery
            _scheduler = LocalCelery("evoloop_local")
            logger.warning("[QueueFactory] Using deprecated LocalCelery scheduler")
        except Exception as e:
            logger.error(f"[QueueFactory] Failed to create LocalCelery: {e}")
            raise RuntimeError("No task scheduler available")
    
    return _scheduler


def get_scheduler() -> TaskScheduler:
    """
    Get global scheduler instance (singleton).
    
    Creates scheduler on first call based on configuration.
    Uses TASK_QUEUE_BACKEND setting from config (defaults to "auto").
    
    Returns:
        TaskScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        backend = settings.TASK_QUEUE_BACKEND
        logger.info(f"[QueueFactory] Using configured backend: {backend}")
        _scheduler = create_task_scheduler(backend)
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
    **options
):
    """
    Universal shared_task decorator.
    
    Works with any scheduler (Celery/Huey/LocalCelery).
    
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
    return scheduler.task(
        func,
        name=name,
        bind=bind,
        retries=retries,
        retry_delay=retry_delay,
        **options
    )


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
    if hasattr(scheduler, 'periodic_task'):
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
