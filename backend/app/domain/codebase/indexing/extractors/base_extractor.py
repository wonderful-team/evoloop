"""
Base Extractor Classes
======================

Provides common functionality for semantic extractors (API, DB, etc.)
to reduce code duplication.
"""

import os
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from app.constants import SEMANTIC_LANGUAGE_MAP
from app.utils.file import read_file_content

T = TypeVar('T')


class SemanticExtractorBase(ABC, Generic[T]):
    """
    Base class for semantic extractors (API, DB, etc.).
    
    Provides common functionality:
    - Provider registry access
    - Language detection from file extension
    - Content reading
    """

    def __init__(self):
        from .provider_registry import semantic_provider_registry
        self._registry = semantic_provider_registry

    def _get_provider(self, lang_name: str):
        """Get language provider from registry."""
        return self._registry.get(lang_name)

    def _detect_language(self, file_path: str) -> str | None:
        """
        Detect language from file extension.
        
        Returns:
            Language name (e.g., 'python', 'go') or None if not supported
        """
        ext = os.path.splitext(file_path)[1].lower()
        for name, exts in SEMANTIC_LANGUAGE_MAP.items():
            if ext in exts:
                return name
        return None

    def _read_file(self, file_path: str) -> str | None:
        """Read file content, return None if failed."""
        try:
            content, _ = read_file_content(file_path)
            return content
        except Exception:
            return None

    @abstractmethod
    async def extract(self, file_path: str) -> list[T]:
        """
        Extract entities from file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of extracted entities
        """
        pass

    @abstractmethod
    async def sync_to_graph(self, project_id: int, entities: list[T]):
        """
        Sync extracted entities to Neo4j graph.
        
        Args:
            project_id: Project identifier
            entities: List of entities to sync
        """
        pass
