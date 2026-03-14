"""No-op Graph Navigator for Client mode.

Server mode uses Neo4j for knowledge graph navigation.
Client mode uses cloud API (not yet implemented) or returns empty results.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NoOpGraphNavigator:
    """
    No-op graph navigator for client mode.

    All operations return empty results or None.
    Graph functionality is delegated to cloud API in client mode.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize graph navigator (no-op)."""
        self._initialized = True
        logger.debug("[NoOpGraphNavigator] Initialized")

    async def get_directory_info(self, project_id: int, path: str) -> dict[str, Any]:
        """
        Get architecture summary for a directory.

        Client mode: Returns basic info without graph relationships.
        """
        logger.debug(f"[NoOpGraphNavigator] get_directory_info({project_id}, {path}) - returning empty")
        return {
            "path": path,
            "summary": "Graph navigation not available in client mode (use cloud API)",
            "sub_modules": [],
            "dependencies": [],
        }

    async def get_node_details(
        self, node_type: str, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Get details for specific graph nodes.

        Client mode: Returns empty list.
        """
        return []

    async def traverse(
        self, start_id: str, rel_type: str, max_depth: int = 2
    ) -> list[dict[str, Any]]:
        """
        Traverse graph relationships.

        Client mode: Returns empty list.
        """
        return []

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Search the knowledge graph.

        Client mode: Returns empty list.
        """
        return []

    async def semantic_search(
        self, query: str, project_id: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Semantic search in the knowledge graph.

        Client mode: Returns empty list.
        """
        logger.debug(f"[NoOpGraphNavigator] semantic_search('{query}') - returning empty")
        return []

    async def flush(self) -> None:
        """Flush pending operations (no-op)."""
        pass
