
import asyncio
import logging
from app.celery_app import celery_app
from app.domain.codebase.indexing.manager import indexing_manager

logger = logging.getLogger(__name__)

@celery_app.task(name="run_full_indexing")
def run_full_indexing_task(project_id: int, rebuild: bool = False):
    """
    Celery task to run full indexing in a background worker.
    """
    logger.info(f"[Celery] Starting Full Indexing for Project {project_id} (Rebuild={rebuild})")
    try:
        # Since indexing_manager methods are async, we need to run them in an event loop.
        # Check if we are already in loop? Celery workers are usually sync.
        
        loop = asyncio.get_event_loop()
        if loop.is_closed():
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             
        # We invoke the logic directly.
        # Note: indexing_manager instance here is likely a NEW instance in the worker process.
        # This is fine as it relies on DB/Neo4j, which are shared.
        # However, IN-MEMORY status tracking (self._active_jobs) will NOT sync back to Web Server.
        # We need Redis-based status if we want visibility.
        # For now, we run the logic.
        
        loop.run_until_complete(indexing_manager.trigger_full_index(project_id, rebuild))
        
        logger.info(f"[Celery] Full Indexing Completed for Project {project_id}")
    except Exception as e:
        logger.error(f"[Celery] Indexing Task Failed: {e}")
