"""
Bridge Tools.
Allows the new Brain to access the legacy app.core.memory module.
"""
import logging

from app.core.memory.manager import memory_manager

logger = logging.getLogger(__name__)


class GraphMemoryTool:
    """
    A Tool exposed to the Brain to query the Knowledge Graph.
    """

    @staticmethod
    async def query_codebase(query: str) -> str:
        """
        Searches the codebase graph.
        """
        try:
            # Assuming memory_manager.graph has a search method or similar
            # Based on memory/README.md, it has get_node_details etc.
            # We map a generic search to one of these or just mock it if not strictly available
            # Real implementation would call memory_manager.long_term.search_concepts
            results = await memory_manager.long_term.search_concepts(query, project_id=1) # TODO: Pass project_id
            return str([r.__dict__ for r in results])
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return f"Error querying graph: {e}"

    @staticmethod
    async def record_fact(fact: str):
        """
        Saves a fact to the old memory.
        """
        # Mock implementation bridging to old memory
        pass
