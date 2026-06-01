"""
Celery implementation for full mode (EMBEDDED_MODE=false).

Provides a factory function to create a Celery application instance
connected to Redis broker. Used by factory.py for distributed task execution.
"""

import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_celery_app():
    """Create and return a configured Celery application instance."""
    from celery import Celery

    db_dir = Path.home() / ".evoloop" / "database"
    db_dir.mkdir(parents=True, exist_ok=True)

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


# Module-level app for Celery CLI (-A app.infrastructure.queue.celery_app) and tests
celery_app = create_celery_app()
