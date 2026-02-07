"""Unified Memory Manager facade."""

import logging

from app.core.memory.backends.neo4j_graph import Neo4jGraphNavigator
from app.core.memory.backends.neo4j_long_term import Neo4jLongTermMemory
from app.core.memory.backends.neo4j_preferences import Neo4jPreferenceStore
from app.core.memory.backends.sql_short_term import SqlShortTermMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified facade for the memory system.
    Provides a single entry point for all memory operations.
    """

    def __init__(self):
        """Initialize memory components."""
        self.long_term = Neo4jLongTermMemory()
        self.preferences = Neo4jPreferenceStore()
        self.graph = Neo4jGraphNavigator()
        self.short_term = SqlShortTermMemory()
        logger.info("MemoryManager: Initialized with Neo4j + SQL backends")

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


# Global instance
memory_manager = MemoryManager()
