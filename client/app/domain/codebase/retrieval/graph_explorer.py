"""Graph Explorer - Server-only feature (Neo4j required).

This module is a stub in the client branch. Graph exploration
requires Neo4j graph database which is only available in server mode.
"""
import logging

logger = logging.getLogger(__name__)


class GraphExplorer:
    """
    Exploratory Graph Retrieval - Server-only feature.

    Client mode uses Cloud API for graph queries instead.
    """

    def __init__(self):
        self.graph = None
        self._chain = None
        logger.info("[GraphExplorer] Client mode - graph queries use cloud API")

    async def query(self, question: str, project_id: int | None = None) -> str:
        """
        Ask a natural language question about the graph.

        Client mode: Delegated to cloud API.
        """
        return "[Client Mode] Graph queries are handled via Cloud API."


# Global instance
graph_explorer = GraphExplorer()
