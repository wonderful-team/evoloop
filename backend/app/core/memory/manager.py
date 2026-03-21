"""Unified Memory Manager facade."""

import logging

from app.core.config import settings
from app.core.memory.backends.sql_short_term import SqlShortTermMemory

logger = logging.getLogger(__name__)

# Conditional imports based on mode
if settings.EMBEDDED_MODE:
    from app.core.memory.backends.noop_memory import (
        NoOpGraphNavigator,
        NoOpLongTermMemory,
        NoOpPreferenceStore,
    )
else:
    from app.core.memory.backends.neo4j_graph import Neo4jGraphNavigator
    from app.core.memory.backends.neo4j_long_term import Neo4jLongTermMemory
    from app.core.memory.backends.neo4j_preferences import Neo4jPreferenceStore


class MemoryManager:
    """
    Unified facade for the memory system.
    Provides a single entry point for all memory operations.
    """

    def __init__(self):
        """Initialize memory components."""
        if settings.EMBEDDED_MODE:
            self.long_term = NoOpLongTermMemory()
            self.preferences = NoOpPreferenceStore()
            self.graph = NoOpGraphNavigator()
            logger.info("MemoryManager: Initialized with NoOp + SQL backends (embedded mode)")
        else:
            self.long_term = Neo4jLongTermMemory()
            self.preferences = Neo4jPreferenceStore()
            self.graph = Neo4jGraphNavigator()
            logger.info("MemoryManager: Initialized with Neo4j + SQL backends")
        self.short_term = SqlShortTermMemory()

    async def initialize(self) -> None:
        """Initialize all memory components."""
        await self.long_term.initialize()
        await self.preferences.initialize()
        await self.graph.initialize()
        await self.short_term.initialize()
        logger.info("MemoryManager: All components initialized")

    async def flush(self) -> None:
        """Flush all memory components (for testing)."""
        await self.long_term.flush()
        await self.preferences.flush()
        await self.graph.flush()
        await self.short_term.flush()
        logger.info("MemoryManager: All components flushed")

    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10):
        """Search conversation history."""
        return await self.short_term.search_messages(query, thread_id, limit)


# Global instance
memory_manager = MemoryManager()
