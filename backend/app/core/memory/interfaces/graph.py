"""Graph navigation interface for structural insights (GraphRAG)."""

from abc import abstractmethod
from typing import Any, Dict, List

from app.core.memory.interfaces.base import IMemoryProvider


class IGraphNavigator(IMemoryProvider):
    """
    Interface for navigating knowledge graphs and extracting structural insights.
    Supports GraphRAG patterns for understanding codebase architecture.
    """

    @abstractmethod
    async def get_node_details(self, node_type: str, filters: Dict[str, Any]) -> dict:
        """
        Retrieve detailed information about a specific node.

        Args:
            node_type: Type of node to query (e.g., "Directory", "CodeEntity")
            filters: Dictionary of filters to apply (e.g., {"path": "app/core", "project_id": 1})

        Returns:
            Dictionary containing node details, relationships, and metadata
        """
        pass

    @abstractmethod
    async def traverse(
        self, start_node_id: str, relation_type: str, max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Traverse the graph from a starting node following specific relationships.

        Args:
            start_node_id: Starting node identifier
            relation_type: Type of relationship to follow (e.g., "DEPENDS_ON", "CONTAINS")
            max_depth: Maximum traversal depth

        Returns:
            List of nodes encountered during traversal
        """
        pass

    @abstractmethod
    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """
        Retrieve architectural summary for a directory.

        Args:
            project_id: Project identifier
            path: Directory path

        Returns:
            Dictionary with summary, sub-modules, and dependencies
        """
        pass
