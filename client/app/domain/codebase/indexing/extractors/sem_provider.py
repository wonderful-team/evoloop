from abc import ABC, abstractmethod
from typing import Any


class LanguageSemanticProvider(ABC):
    """
    Abstract provider for language-specific semantic analysis.
    Each language (Python, Go, etc.) implements this.

    Provides queries for:
    - API extraction (get_api_query)
    - Code structure extraction (get_structure_query)
    - Import extraction (get_imports_query)
    - DB schema extraction (extract_db)
    """

    @abstractmethod
    def get_language_name(self) -> str:
        """Return the unique key for this language (e.g. 'python')"""
        pass

    @abstractmethod
    def get_api_query(self) -> str:
        """Return the Tree-sitter query string for API extraction"""
        pass

    @abstractmethod
    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        """Convert Tree-sitter captures into APIEndpoint objects"""
        pass

    def get_structure_query(self) -> str | None:
        """
        Return the Tree-sitter query for structure extraction (functions, classes).
        Used by TreeSitterExtractor for code indexing.
        Returns None if not implemented (falls back to queries.py).
        """
        return None

    def get_imports_query(self) -> str | None:
        """
        Return the Tree-sitter query for import extraction.
        Returns None if not implemented (falls back to queries.py).
        """
        return None

    def extract_db(self, file_path: str, content: str) -> list[Any]:
        """Generic DB extraction using content (Regex or otherwise)"""
        return []

    def _get_node(self, captured: dict, name: str):
        """
        Helper to safely extract a node from Tree-sitter captures.
        Returns the first node if multiple are captured, or None if not found.
        """
        nodes = captured.get(name)
        if not nodes:
            return None
        return nodes[0] if isinstance(nodes, list) else nodes
