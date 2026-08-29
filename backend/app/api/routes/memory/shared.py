import logging

logger = logging.getLogger(__name__)


async def get_memory_manager():
    """Dependency to get memory manager via MemoryLifespanManager (singleton)."""
    from app.core.memory.lifespan import MemoryLifespanManager

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()

    yield MemoryLifespanManager.get_manager()
