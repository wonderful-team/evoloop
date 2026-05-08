"""
Graph database driver for EvoLoop Backend.

Supports two modes:
- Full mode: Neo4j graph database
- Embedded mode: No-op (graph features disabled)
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.infrastructure.database.graph.file_graph import FileGraphDriver

logger = logging.getLogger(__name__)


# =============================================================================
# NoOp Graph Driver (for Embedded Mode)
# =============================================================================

class NoOpGraphDriver:
    """No-op graph driver for embedded mode."""

    async def execute_query(self, query: str, parameters: dict = None, **kwargs):
        """Execute query (no-op)."""
        logger.debug(f"[NoOpGraph] Query ignored: {query[:50]}...")
        return []

    async def verify_connectivity(self):
        """Verify connectivity (no-op)."""
        return True

    async def close(self):
        """Close driver (no-op)."""
        pass

    def session(self):
        """Return a no-op session context manager."""
        return NoOpGraphSessionContext()


class NoOpGraphSessionContext:
    """Async context manager for no-op sessions."""

    async def __aenter__(self):
        return NoOpGraphSession()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class NoOpGraphSession:
    """No-op graph session for embedded mode."""

    async def run(self, query: str, parameters: dict = None, **kwargs):
        """Run query (no-op)."""
        return NoOpGraphResult()

    async def close(self):
        """Close session (no-op)."""
        pass


class NoOpGraphResult:
    """No-op graph result for embedded mode."""

    def __aiter__(self):
        return iter([])

    async def data(self):
        return []

    async def single(self):
        return None


# =============================================================================
# Neo4j Manager (with embedded mode support)
# =============================================================================

class Neo4jManager:
    _drivers: dict[asyncio.AbstractEventLoop, Any] = {}
    _file_driver: Any = None
    _use_neo4j: bool = settings.USE_NEO4J and not settings.EMBEDDED_MODE

    @classmethod
    def get_driver(cls):
        # Check if Neo4j is disabled
        if not cls._use_neo4j or settings.EMBEDDED_MODE:
            # Use file-based graph in embedded mode
            if cls._file_driver is None:
                try:
                    from app.infrastructure.database.graph.file_graph import FileGraphDriver
                    cls._file_driver = FileGraphDriver()
                    return cls._file_driver
                except ImportError:
                    logger.warning("[Neo4jManager] FileGraphDriver not available, using NoOp")
                    return NoOpGraphDriver()
            return cls._file_driver

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Cannot get Neo4j driver without a running event loop")

        # Check existing driver for this loop
        if loop in cls._drivers:
            driver = cls._drivers[loop]
            return driver

        # Create new driver bound to this loop
        try:
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI or "bolt://localhost:7687",
                auth=(settings.NEO4J_USER or "neo4j", settings.NEO4J_PASSWORD)
            )

            cls._drivers[loop] = driver
            logger.info(f"Connected to Neo4j (Loop: {id(loop)})")
            return driver
        except ImportError:
            logger.warning("Neo4j driver not installed, using NoOp driver")
            cls._use_neo4j = False
            return NoOpGraphDriver()
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            logger.warning("Falling back to NoOp graph driver")
            cls._use_neo4j = False
            return NoOpGraphDriver()

    @classmethod
    async def close_driver(cls):
        """Close driver for current loop"""
        if not cls._use_neo4j:
            return

        try:
            loop = asyncio.get_running_loop()
            if loop in cls._drivers:
                driver = cls._drivers.pop(loop)
                await driver.close()
                logger.info(f"Closed Neo4j connection (Loop: {id(loop)})")
        except RuntimeError:
            pass

    @classmethod
    async def close_all(cls):
        """Close drivers for all loops (e.g. shutdown)"""
        if not cls._use_neo4j:
            return

        for loop, driver in cls._drivers.items():
            try:
                await driver.close()
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver for loop {id(loop)}: {e}")
        cls._drivers.clear()

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if graph features are enabled."""
        # In embedded mode, file-based graph is used
        if settings.EMBEDDED_MODE:
            return cls._file_driver is not None
        return cls._use_neo4j


def is_graph_enabled() -> bool:
    """
    Check if graph features are enabled (regardless of backend implementation).

    Use this instead of Neo4jManager.is_enabled() in business logic to avoid
    hard-coding dependency on a specific graph backend.
    """
    return Neo4jManager.is_enabled()


async def get_graph_db():
    """Get graph database driver (Neo4j or NoOp)."""
    driver = Neo4jManager.get_driver()
    return driver


# Export for compatibility
__all__ = ["Neo4jManager", "get_graph_db", "is_graph_enabled", "NoOpGraphDriver", "FileGraphDriver"]
