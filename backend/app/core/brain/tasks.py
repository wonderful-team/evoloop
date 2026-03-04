import asyncio
import logging

from celery import shared_task

from app.core.brain.consolidation import MemoryConsolidator
from app.core.brain.drivers.llm_driver import ReflectiveDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.config import settings
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@shared_task(name="brain_consolidate_memory")
def consolidate_memory(source_message_id: str = None):
    """
    Background task to run the Brain Sleep Cycle.
    """
    logger.info(f"[Celery] Starting Brain Consolidation Task (Source: {source_message_id})...")

    async def _run():
        fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        fs.initialize()  # Ensure directories exist before reading
        reflective = ReflectiveDriver()
        consolidator = MemoryConsolidator(reflective, fs)
        await consolidator.run_cycle(source_message_id=source_message_id)

    async def _run_with_flush():
        try:
            await _run()
        finally:
            await flush_loop_bound_resources()
            
    # Run in fresh loop
    asyncio.run(_run_with_flush())
    logger.info("[Celery] Brain Consolidation Task Finished.")
