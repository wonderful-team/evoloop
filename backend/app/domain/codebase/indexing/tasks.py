"""
Codebase Indexing Background Tasks.

Runs in Huey (embedded mode) or Celery (full mode) worker.
"""

import asyncio
import logging

from app.infrastructure.queue.factory import shared_task
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@shared_task(name="codebase_index_file")
async def index_file_task(file_path: str, repo_id: int):
    """Background task to index a single modified file."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    await service.index_file(file_path, repo_id)


@shared_task(name="codebase_remove_file")
async def remove_file_task(file_path: str, repo_id: int):
    """Background task to remove a single file from the index."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    await service.remove_file(file_path, repo_id)


@shared_task(name="codebase_move_file")
async def move_file_task(src_path: str, dest_path: str, repo_id: int):
    """Background task to move/rename a single file in the index."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    await service.move_file(src_path, dest_path, repo_id)


@shared_task(name="run_full_indexing")
def run_full_indexing_task(project_id: int, rebuild: bool = False):
    """
    Celery/Huey task to run full indexing in a background worker.
    """
    logger.info(f"[Task] Starting Full Indexing for Project {project_id} (Rebuild={rebuild})")

    from app.core.monitoring.activity import activity_monitor
    from app.domain.codebase.indexing.manager import indexing_manager

    sys_tid = f"sys:{project_id}:indexing"

    async def _monitored_execution():
        try:
            await activity_monitor.start_run(sys_tid, "Full Codebase Indexing")
            await activity_monitor.update_agent_state(sys_tid, "Indexing", "Indexing Codebase", "Initializing...")

            # TODO: We should enhance trigger_full_index to accept a progress callback
            await indexing_manager.trigger_full_index(project_id, rebuild)

            await activity_monitor.end_run(sys_tid, "done")
            logger.info(f"[Task] Full Indexing Completed for Project {project_id}")

        except Exception as e:
            logger.error(f"[Task] Indexing Task Failed: {e}")
            await activity_monitor.end_run(sys_tid, "failed")

    async def _run_with_flush():
        try:
            await _monitored_execution()
        finally:
            await flush_loop_bound_resources()

    asyncio.run(_run_with_flush())
