import logging

from app.core.brain.consolidation import MemoryConsolidator
from app.core.brain.drivers.llm_driver import ReflectiveDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.config import settings
from app.core.interfaces.cleanup import ICleanupHandler

logger = logging.getLogger(__name__)


class BrainCleanupHandler(ICleanupHandler):
    """
    Cleans up Brain-specific artifacts (e.g. Journal entries)
    linked to rolled-back messages.
    """

    def __init__(self):
        # Lazy load dependencies if needed, or init here
        # We need filesystem and maybe drivers
        self.fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        # Consolidator needs a driver, but for cleanup we might only need FS access?
        # Actually remove_entry_by_id is on Consolidator, so we should instantiate it.
        # But Consolidator needs LLM driver... verifying if remove_entry_by_id uses LLM.
        # Check consolidation.py: remove_entry_by_id only uses regex and FS.
        # So we can pass a dummy or None for driver if we are careful, or just instantiate ReflectiveDriver.
        self.reflective = ReflectiveDriver()
        self.consolidator = MemoryConsolidator(self.reflective, self.fs)

    async def cleanup(self, message_ids: list[str]) -> int:
        count = 0
        for mid in message_ids:
            if await self.consolidator.remove_entry_by_id(mid):
                count += 1

        if count > 0:
            logger.info(f"[BrainCleanup] Removed {count} journal entries.")
        return count
