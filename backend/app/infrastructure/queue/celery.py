from pathlib import Path

from celery import Celery

from app.core.config import settings

# Ensure database directory exists for Celery beat schedule
db_dir = Path.home() / ".evoloop" / "database"
db_dir.mkdir(parents=True, exist_ok=True)

celery_app = Celery(
    "evoloop_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.domain.codebase.indexing.tasks",
        "app.domain.project.summarizer",
        "app.domain.project.sync_tasks",
        "app.domain.wiki.tasks",
        "app.core.brain.tasks",
        "app.core.engine.tasks",
        "app.core.atlas.tasks",
        "app.core.vision.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule_filename=str(db_dir / "celerybeat-schedule.db"),
    beat_schedule={
        # Storage cleanup tasks - run daily at low-traffic hours
        "cleanup-screenshots-daily": {
            "task": "app.core.vision.cleanup_screenshots",
            "schedule": 86400.0,  # 24 hours
            "args": (False,),     # dry_run=False
        },
        "cleanup-screen-recordings-daily": {
            "task": "app.core.vision.cleanup_screen_recordings",
            "schedule": 86400.0,  # 24 hours
            "args": (False,),     # dry_run=False
        },
        "autonomous-scheduler-tick": {
            "task": "engine_scheduler_tick",
            "schedule": 60.0,  # Every 1 minute
        },
    },
)
