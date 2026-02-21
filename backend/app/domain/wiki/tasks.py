import asyncio
import logging
from celery import shared_task
from app.domain.wiki.service import wiki_service
from app.infrastructure.llm.factory import get_default_llm


@shared_task(name="wiki_generate")
def generate_wiki_task(project_id: int, topic: str, force_regenerate: bool = False):
    """
    Celery task to generate wiki pages in background.
    """
    from app.core.monitoring.activity import activity_monitor
    
    sys_tid = f"sys:{project_id}:wiki"
    logger = logging.getLogger(__name__)

    async def _monitored_execution():
        try:
            logger.info(f"[Celery] Starting Wiki Generation for Project {project_id}")
            await activity_monitor.start_run(sys_tid, f"Wiki Generation: {topic}")
            await activity_monitor.update_agent_state(sys_tid, "WIKI", "Generating Wiki", "Deep Research in progress...")
            
            # Instantiate LLM inside the worker process
            llm = get_default_llm()
            
            # Run async service
            await wiki_service.generate_wiki(
                project_id=project_id, 
                topic=topic, 
                llm=llm, 
                force_regenerate=force_regenerate
            )
            
            await activity_monitor.end_run(sys_tid, "done")
            logger.info(f"[Celery] Wiki Generation Completed for Project {project_id}")
            
        except Exception as e:
            logger.error(f"[Celery] Wiki Task Failed: {e}")
            await activity_monitor.end_run(sys_tid, "failed")

    # Run async function
    asyncio.run(_monitored_execution())
    
    return f"Wiki generated for Project {project_id}"
