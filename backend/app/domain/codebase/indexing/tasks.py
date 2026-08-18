"""
Codebase Indexing Background Tasks.

Runs in Huey (embedded mode) or Celery (full mode) worker.
All tasks have a built-in timeout so a single hanging file can't
stall the entire worker queue.
"""

import asyncio
import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)

_INDEX_TIMEOUT = 120.0
"""Max seconds a single index_file call may take before asyncio.TimeoutError."""


@shared_task(name="codebase_index_file")
async def index_file_task(file_path: str, repo_id: int) -> None:
    """Background task to index a single modified file."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    try:
        await asyncio.wait_for(
            service.index_file(file_path, repo_id),
            timeout=_INDEX_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[Task] index_file timed out after {_INDEX_TIMEOUT}s: {file_path}"
        , exc_info=True)
    except Exception:
        logger.exception(f"[Task] index_file failed: {file_path}")


@shared_task(name="codebase_remove_file")
async def remove_file_task(file_path: str, repo_id: int) -> None:
    """Background task to remove a single file from the index."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    try:
        await asyncio.wait_for(
            service.remove_file(file_path, repo_id),
            timeout=_INDEX_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[Task] remove_file timed out after {_INDEX_TIMEOUT}s: {file_path}"
        , exc_info=True)
    except Exception:
        logger.exception(f"[Task] remove_file failed: {file_path}")


@shared_task(name="codebase_move_file")
async def move_file_task(src_path: str, dest_path: str, repo_id: int) -> None:
    """Background task to move/rename a single file in the index."""
    from app.domain.codebase.indexing.service import IndexingService

    service = IndexingService()
    try:
        await asyncio.wait_for(
            service.move_file(src_path, dest_path, repo_id),
            timeout=_INDEX_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[Task] move_file timed out after {_INDEX_TIMEOUT}s: {src_path} -> {dest_path}"
        , exc_info=True)
    except Exception:
        logger.exception(f"[Task] move_file failed: {src_path} -> {dest_path}")


@shared_task(name="run_full_indexing")
async def run_full_indexing_task(repo_id: int, rebuild: bool = False) -> None:
    """
    Celery/Huey task to run full indexing in a background worker.
    """
    logger.info(f"[Task] Starting Full Indexing for Repo {repo_id} (Rebuild={rebuild})")

    from app.core.monitoring.activity import activity_monitor
    from app.domain.codebase.indexing.manager import indexing_manager

    sys_tid = f"sys:{repo_id}:indexing"

    try:
        await activity_monitor.start_run(sys_tid, "Full Codebase Indexing")
        await activity_monitor.update_agent_state(sys_tid, "Indexing", "Indexing Codebase", "Initializing...")

        await indexing_manager.trigger_full_index_repo(repo_id, rebuild)

        await activity_monitor.end_run(sys_tid, "done")
        logger.info(f"[Task] Full Indexing Completed for Repo {repo_id}")

    except asyncio.CancelledError:
        logger.warning(f"[Task] Full indexing cancelled for Repo {repo_id}", exc_info=True)
        await activity_monitor.end_run(sys_tid, "cancelled")
        raise
    except Exception as e:
        logger.exception(f"[Task] Indexing Task Failed: {e}")
        await activity_monitor.end_run(sys_tid, "failed")
