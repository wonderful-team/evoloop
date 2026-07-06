"""
Unified Graph Database Management for EvoLoop.

This module provides a consistent interface (GraphManager) to access either
a full Neo4j graph database or a local file-based graph (FileGraph).
"""

import asyncio
import logging
import threading
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
    Manages graph database drivers across multiple event loops and projects.
    Dispatches to Neo4j or FileGraph based on configuration.

    缓存策略：
    - Embedded Mode: 按 (loop, project_path) 缓存 FileGraphDriver 实例
    - Full Mode: 按 loop 缓存 Neo4jDriver 实例（Neo4j 是全局共享的）

    Thread-safety:
        A threading.Lock protects the shared driver cache so that multiple
        Huey worker threads can safely call get_driver concurrently.
    """
    # Key: (event_loop, project_path) for FileGraph; (event_loop, None) for Neo4j
    _drivers: dict[tuple[asyncio.AbstractEventLoop, str | None], IGraphDriver] = {}
    _lock = threading.Lock()

    @classmethod
    def get_driver(cls, project_path: str | None = None) -> IGraphDriver:
        """
        Get the graph driver for the current event loop and project.

        Args:
            project_path: 项目本地路径（如 /Users/xujin/Projects/evoloop）。
                         Embedded Mode 下，每个 project_path 对应一个独立的 FileGraphDriver。
                         None 表示全局 driver（Atlas 等非项目数据使用）。

        Returns:
            IGraphDriver: FileGraphDriver (embedded) 或 Neo4jDriver (full mode)
        """
        # 1. Handle Embedded Mode (File-based Graph)
        if settings.EMBEDDED_MODE:
            from app.infrastructure.database.graph.file_graph import FileGraphDriver

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Fallback for non-async context
                return FileGraphDriver(project_path=project_path)

            cache_key = (loop, project_path)
            with cls._lock:
                if cache_key not in cls._drivers:
                    cls._drivers[cache_key] = FileGraphDriver(project_path=project_path)
                    logger.debug(f"[GraphManager] Created FileGraphDriver for project_path={project_path}")
                return cls._drivers[cache_key]

        # 2. Handle Full Mode (Neo4j) - Neo4j is global, no project isolation
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Cannot get Graph driver without a running event loop")

        cache_key = (loop, None)
        with cls._lock:
            if cache_key in cls._drivers:
                return cls._drivers[cache_key]

        # Initialize Neo4j Driver outside the lock so the (potentially slow)
        # connection setup does not block other threads.
        from app.infrastructure.database.graph.neo4j import Neo4jDriver

        driver = Neo4jDriver(
            uri=settings.NEO4J_URI or "bolt://localhost:7687",
            user=settings.NEO4J_USER or "neo4j",
            password=settings.NEO4J_PASSWORD
        )

        with cls._lock:
            if cache_key not in cls._drivers:
                cls._drivers[cache_key] = driver
            logger.info(f"Connected to Neo4j (Loop: {id(loop)})")
            return cls._drivers[cache_key]

    @classmethod
    async def close_driver(cls, project_path: str | None = None):
        """Close driver for the current loop and project."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        cache_key = (loop, project_path)
        with cls._lock:
            if cache_key not in cls._drivers:
                return
            driver = cls._drivers.pop(cache_key)
        await driver.close()
        logger.info(f"Closed Graph connection (Loop: {id(loop)}, project: {project_path})")

    @classmethod
    async def close_all(cls):
        """Close drivers for all loops and projects (e.g. on shutdown)."""
        with cls._lock:
            # Copy the items so we can close them without mutating the dict
            # while iterating.
            items = list(cls._drivers.items())
            cls._drivers.clear()
        for cache_key, driver in items:
            try:
                await driver.close()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"Error closing Graph driver for {cache_key}: {e}")

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if graph features are enabled.

        Graph features (Neo4j Cypher queries) are only available in server mode.
        In embedded mode FileGraph is available but does not support Cypher.
        """
        return not settings.EMBEDDED_MODE


# =============================================================================
# Standard Helper Functions
# =============================================================================

async def get_graph_db(project_path: str | None = None) -> IGraphDriver:
    """
    Convenience helper to get the active graph driver.

    Args:
        project_path: 项目本地路径。Embedded Mode 下用于获取项目级 driver。
                     None 表示全局 driver。
    """
    return GraphManager.get_driver(project_path=project_path)


def is_graph_enabled() -> bool:
    """Public check for graph feature availability."""
    return GraphManager.is_enabled()


__all__ = ["GraphManager", "get_graph_db", "is_graph_enabled", "IGraphDriver"]
