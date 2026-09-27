"""
Codebase Indexing Background Tasks.

Runs in Huey (embedded mode) or Celery (full mode) worker.
"""

import asyncio
import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="run_full_indexing")
async def run_full_indexing_task(repo_id: int, rebuild: bool = False) -> None:
    """
    Celery/Huey task to run full indexing in a background worker.
    """
    logger.info(f"[Task] Starting Full Indexing for Repo {repo_id} (Rebuild={rebuild})")

    from app.core.monitoring.activity import activity_monitor
    from app.core.monitoring.constants import ActivityStatus
    from app.domain.codebase.indexing.manager import indexing_manager

    sys_tid = f"sys:{repo_id}:indexing"

    try:
        await activity_monitor.start_run(sys_tid, "Full Codebase Indexing")
        await activity_monitor.update_agent_state(
            sys_tid, "Indexing", "Indexing Codebase", "Initializing..."
        )

        await indexing_manager.trigger_full_index_repo(repo_id, rebuild)

        await activity_monitor.end_run(sys_tid, ActivityStatus.DONE)
        logger.info(f"[Task] Full Indexing Completed for Repo {repo_id}")

    except asyncio.CancelledError:
        logger.warning(
            f"[Task] Full indexing cancelled for Repo {repo_id}", exc_info=True
        )
        await activity_monitor.end_run(sys_tid, ActivityStatus.CANCELLED)
        raise
    except Exception as e:
        logger.exception(f"[Task] Indexing Task Failed: {e}")
        await activity_monitor.end_run(sys_tid, ActivityStatus.FAILED)
