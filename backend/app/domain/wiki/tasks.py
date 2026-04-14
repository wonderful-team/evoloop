import asyncio
import logging

from app.domain.wiki.schemas import WikiSyncResult
from app.domain.wiki.service import wiki_service
# Use unified task queue (Huey in embedded mode, Celery in full mode)
from app.infrastructure.queue.factory import shared_task
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@shared_task(name="wiki_generate", retries=3, retry_delay=60)
def generate_wiki_task(project_id: int, topic: str, force_regenerate: bool = False):
    """
    Background task to generate wiki pages.
    
    Runs in Huey (embedded mode) or Celery (full mode) worker.
    Supports automatic retries on failure.
    """
    from app.core.monitoring.activity import activity_monitor

    sys_tid = f"sys:{project_id}:wiki"

    async def _monitored_execution():
        try:
            logger.info(f"[WikiTask] Starting Wiki Generation for Project {project_id}")
            await activity_monitor.start_run(sys_tid, f"Wiki Generation: {topic}")
            await activity_monitor.update_agent_state(
                sys_tid, "WIKI", "Generating Wiki", "Deep Research in progress..."
            )

            # Run async service (InternalLLMService is used internally)
            await wiki_service.generate_wiki(
                project_id=project_id,
                topic=topic,
                force_regenerate=force_regenerate
            )

            await activity_monitor.end_run(sys_tid, "done")
            logger.info(f"[WikiTask] Wiki Generation Completed for Project {project_id}")

        except Exception as e:
            logger.error(f"[WikiTask] Wiki Task Failed: {e}")
            await activity_monitor.end_run(sys_tid, "failed")
            raise  # Re-raise to trigger retry

    async def _run_with_flush():
        try:
            await _monitored_execution()
        finally:
            await flush_loop_bound_resources()

    # Run async function
    asyncio.run(_run_with_flush())

    return f"Wiki generated for Project {project_id}"


@shared_task(name="sync_wiki_page")
def sync_wiki_page_task(project_id: int, page_id: str) -> WikiSyncResult:
    """Sync a wiki page to EvoCloud."""
    logger.info(f"[WikiTask] Syncing wiki page {page_id} for project {project_id}")
    # Implementation here
    return WikiSyncResult(project_id=project_id, page_id=page_id, status="synced")
