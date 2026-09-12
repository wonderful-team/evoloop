"""
Celery implementation for full mode (EMBEDDED_MODE=false).

Provides a factory function to create a Celery application instance
connected to Redis broker. Used by factory.py for distributed task execution.
"""

import logging

from celery.signals import setup_logging, worker_process_init

from app.core.config import settings

logger = logging.getLogger(__name__)


@setup_logging.connect
def config_loggers(*args, **kwargs):
    """
    Hook into Celery's logging setup to ensure our app's custom logging configuration
    is applied to both the main Celery process and any spawned worker processes.
    """
    from app.logging import setup_logging as app_setup_logging

    app_setup_logging()

    # Also ensure celery task logger propagates or we configure root
    # setup_logging() already sets the root logger, which handles everything.


@worker_process_init.connect
def on_worker_init(*args, **kwargs):
    """
    Hook into Celery worker child process initialization to ensure all in-process
    event handlers (like MemoryRewind) are auto-discovered and registered.
    """
    from app.core.events.discovery import auto_discover_handlers

    try:
        auto_discover_handlers()
        logger.info("[Task] All event handlers auto-discovered and registered in worker process.")
    except (ImportError, ValueError) as e:
        logger.error(
            "[Task] Failed to auto-discover event handlers in worker: %s", e, exc_info=True
        )


def create_celery_app():
    """Create and return a configured Celery application instance."""
    import os

    from celery import Celery

    os.makedirs(os.path.dirname(settings.CELERY_SCHEDULE_DB_PATH), exist_ok=True)

    from app.infrastructure.queue.discovery import discover_task_modules

    app = Celery(
        "evoloop_worker",
        broker=settings.REDIS_URL or "redis://localhost:6379/0",
        backend=settings.REDIS_URL or "redis://localhost:6379/0",
        include=discover_task_modules(),
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        beat_schedule_filename=settings.CELERY_SCHEDULE_DB_PATH,
        beat_schedule={
            "cleanup-screenshots-daily": {
                "task": "app.infrastructure.vision.cleanup_screenshots",
                "schedule": 86400.0,
                "args": (False,),
            },
            "cleanup-screen-recordings-daily": {
                "task": "app.infrastructure.vision.cleanup_screen_recordings",
                "schedule": 86400.0,
                "args": (False,),
            },
            "autonomous-scheduler-tick": {
                "task": "engine_scheduler_tick",
                "schedule": 60.0,
            },
        },
    )

    logger.info("[Task] Full mode enabled with Redis broker")
    return app


# Module-level app for Celery CLI (-A app.infrastructure.queue.celery_app) and tests
celery_app = create_celery_app()
