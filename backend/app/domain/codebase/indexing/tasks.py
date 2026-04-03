import asyncio
import logging

# Unified task queue (Huey in embedded mode, Celery in full mode)
from app.infrastructure.queue.factory import get_scheduler

# Get scheduler instance
_task_scheduler = get_scheduler()

# Create task decorator
def _task(name, **kwargs):
    def decorator(f):
        return _task_scheduler.task(f, name=name, **kwargs)
    return decorator
from app.domain.codebase.indexing.manager import indexing_manager
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@_task(name="run_full_indexing")
def run_full_indexing_task(project_id: int, rebuild: bool = False):
    """
    Celery task to run full indexing in a background worker.
    """
    logger.info(f"[Celery] Starting Full Indexing for Project {project_id} (Rebuild={rebuild})")

    from app.core.monitoring.activity import activity_monitor

    sys_tid = f"sys:{project_id}:indexing"

    async def _monitored_execution():
        try:
            await activity_monitor.start_run(sys_tid, "Full Codebase Indexing")
            await activity_monitor.update_agent_state(sys_tid, "Indexing", "Indexing Codebase", "Initializing...")

            # TODO: We should enhance trigger_full_index to accept a progress callback
            await indexing_manager.trigger_full_index(project_id, rebuild)

            await activity_monitor.end_run(sys_tid, "done")
            logger.info(f"[Celery] Full Indexing Completed for Project {project_id}")

        except Exception as e:
            logger.error(f"[Celery] Indexing Task Failed: {e}")
            await activity_monitor.end_run(sys_tid, "failed")

    async def _run_with_flush():
        try:
            await _monitored_execution()
        finally:
            await flush_loop_bound_resources()

    asyncio.run(_run_with_flush())
