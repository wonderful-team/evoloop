"""
Unified Graph Database Management for EvoLoop.

This module provides a consistent interface (GraphManager) to access either
a full Neo4j graph database or a local file-based graph (FileGraph).
"""

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class IGraphDriver(Protocol):
    """Protocol defining the interface for all graph drivers."""

    async def verify_connectivity(self) -> bool: ...

    async def close(self) -> None: ...

    def session(self) -> Any: ...

    async def execute_query(self, query: str, parameters: dict | None = None, **kwargs) -> list[dict]: ...

    # --- High Level Agnostic API ---

    async def upsert_node(self, label: str, id_field: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Create or update a node. id_field specifies the uniqueness property."""
        ...

    async def find_nodes(self, label: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Find nodes matching the given property filters."""
        ...

    async def delete_nodes(self, label: str, filters: dict[str, Any] | None = None, detach: bool = True) -> int:
        """Delete nodes matching filters. Returns number of deleted nodes."""
        ...

    async def link_nodes(
        self,
        src_label: str,
        src_filters: dict,
        tgt_label: str,
        tgt_filters: dict,
        rel_type: str,
        rel_props: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two sets of nodes."""
        ...

    async def traverse(
        self,
        start_label: str,
        start_filters: dict,
        rel_type: str,
        target_label: str | None = None,
        direction: str = "out",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Traverse the graph from starting nodes following a relationship type."""
        ...

    async def search_similar(
        self,
        label: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform a vector similarity search on nodes with the given label."""
        ...


class GraphManager:
    """
    Manages graph database drivers across multiple event loops.
    Dispatches to Neo4j or FileGraph based on configuration.
    """
    _drivers: dict[asyncio.AbstractEventLoop, IGraphDriver] = {}
    _use_neo4j: bool = settings.USE_NEO4J and not settings.EMBEDDED_MODE

    @classmethod
    def get_driver(cls) -> IGraphDriver:
        """
        Get the graph driver for the current event loop.
        In Embedded Mode, returns FileGraphDriver.
        In Full Mode, returns Neo4jDriver.
        """
        # 1. Handle Embedded Mode (File-based Graph)
        if settings.EMBEDDED_MODE or not cls._use_neo4j:
            from app.infrastructure.database.graph.file_graph import FileGraphDriver

            # We don't cache FileGraphDriver per loop since it's typically used
            # in single-threaded/embedded scenarios, but for consistency we can.
            # However, FileGraphDriver handles its own state.
            try:
                loop = asyncio.get_running_loop()
                if loop not in cls._drivers:
                    cls._drivers[loop] = FileGraphDriver()
                return cls._drivers[loop]
            except RuntimeError:
                # Fallback for non-async context if needed (though rare in backend)
                return FileGraphDriver()

        # 2. Handle Full Mode (Neo4j)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Cannot get Graph driver without a running event loop")

        if loop in cls._drivers:
            return cls._drivers[loop]

        # Initialize Neo4j Driver
        try:
            from app.infrastructure.database.graph.neo4j import Neo4jDriver

            driver = Neo4jDriver(
                uri=settings.NEO4J_URI or "bolt://localhost:7687",
                user=settings.NEO4J_USER or "neo4j",
                password=settings.NEO4J_PASSWORD
            )
            cls._drivers[loop] = driver
            logger.info(f"Connected to Neo4j (Loop: {id(loop)})")
            return driver
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}. Falling back to FileGraph.")
            cls._use_neo4j = False
            # Recurse to get FileGraph fallback
            return cls.get_driver()

    @classmethod
    async def close_driver(cls):
        """Close driver for the current loop."""
        try:
            loop = asyncio.get_running_loop()
            if loop in cls._drivers:
                driver = cls._drivers.pop(loop)
                await driver.close()
                logger.info(f"Closed Graph connection (Loop: {id(loop)})")
        except RuntimeError:
            pass

    @classmethod
    async def close_all(cls):
        """Close drivers for all loops (e.g. on shutdown)."""
        for loop, driver in list(cls._drivers.items()):
            try:
                await driver.close()
            except Exception as e:
                logger.warning(f"Error closing Graph driver for loop {id(loop)}: {e}")
        cls._drivers.clear()

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if graph features are enabled (always true if FileGraph exists)."""
        return True


# =============================================================================
# Standard Helper Functions
# =============================================================================

async def get_graph_db() -> IGraphDriver:
    """Convenience helper to get the active graph driver."""
    return GraphManager.get_driver()


def is_graph_enabled() -> bool:
    """Public check for graph feature availability."""
    return GraphManager.is_enabled()


__all__ = ["GraphManager", "get_graph_db", "is_graph_enabled", "IGraphDriver"]
