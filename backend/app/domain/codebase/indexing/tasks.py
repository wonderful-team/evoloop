
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
    
    from app.core.monitoring.activity import activity_monitor
    sys_tid = f"sys:{project_id}:indexing"
    
    # Run async logic in loop
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    async def _monitored_execution():
        try:
            await activity_monitor.start_run(sys_tid, "Full Codebase Indexing")
            await activity_monitor.update_agent_state(sys_tid, "INDEXING", "Indexing Codebase", "Initializing...")
            
            # TODO: We should enhance trigger_full_index to accept a progress callback
            await indexing_manager.trigger_full_index(project_id, rebuild)
            
            await activity_monitor.end_run(sys_tid, "done")
            logger.info(f"[Celery] Full Indexing Completed for Project {project_id}")
            
        except Exception as e:
            logger.error(f"[Celery] Indexing Task Failed: {e}")
            await activity_monitor.end_run(sys_tid, "failed")
            
    loop.run_until_complete(_monitored_execution())
