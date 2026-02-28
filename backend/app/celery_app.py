from celery import Celery

from app.core.config import settings

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
    beat_schedule={
        "update-skill-embeddings-every-5-minutes": {
            "task": "learning_embed_skills",
            "schedule": 300.0,  # 5 minutes
            "args": (50,),     # batch size
        },
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
    },
)
