"""Unified Memory Manager facade."""

import logging

from app.core.memory.backends.sql_short_term import SqlShortTermMemory
from app.core.memory.backends.sql_preferences import SqlPreferenceStore
from app.core.memory.backends.noop_graph import NoOpGraphNavigator
from app.core.memory.cloud_adapter import CloudLTM

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified facade for the memory system.
    Provides a single entry point for all memory operations.

    Client-only implementation:
    - Uses Cloud LTM (via HTTP API) + SQL short-term + SQL preferences + NoOp graph
    """

    def __init__(self):
        """Initialize memory components."""
        self.short_term = SqlShortTermMemory()
        self.long_term = CloudLTM()
        self.preferences = SqlPreferenceStore()  # SQLite-based preferences
        self.graph = NoOpGraphNavigator()  # Graph navigation via cloud API (or no-op for now)
        logger.info("MemoryManager: Initialized with Cloud LTM + SQL backends")

    async def initialize(self) -> None:
        """Initialize all memory components."""
        await self.long_term.initialize()
        await self.short_term.initialize()
        await self.preferences.initialize()
        await self.graph.initialize()
        logger.info("MemoryManager: All components initialized")

    async def flush(self) -> None:
        """Flush all memory components (for testing)."""
        await self.long_term.flush()
        await self.short_term.flush()
        await self.preferences.flush()
        await self.graph.flush()
        logger.info("MemoryManager: All components flushed")


# Global instance
memory_manager = MemoryManager()
