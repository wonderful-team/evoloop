from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "evoloop_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.domain.codebase.indexing.tasks",
        "app.domain.project.summarizer",
        "app.domain.project.sync_tasks"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
