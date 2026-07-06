"""
Code Analyzer Module
===================

Thin wrapper around TreeSitterExtractor for code analysis.
Provides a synchronous, simplified interface for file analysis.

Note: This module delegates to TreeSitterExtractor to avoid duplication.
Previous standalone implementation was merged to eliminate redundancy.
"""

import logging
from typing import Any

from app.core.file import get_file_ext
from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.domain.codebase.indexing.parsers import parser_registry

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """
    Code Analyzer - Synchronous wrapper for TreeSitterExtractor.
    
    Provides backward-compatible analyze_file() API while delegating
    actual extraction to TreeSitterExtractor.
    """

    def __init__(self):
        self._extractor = TreeSitterExtractor()

    def analyze_file(self, file_path: str, content: str = None) -> dict[str, Any]:
        """
        Analyze a file and return structural info and metrics.
        
        Delegates to TreeSitterExtractor to avoid code duplication.
        
        Args:
            file_path: Path to the file to analyze
            content: Optional file content (read from disk if not provided)
            
        Returns:
            Dictionary with file_path, language, metrics, symbols, and imports
        """
        if content is None:
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Error reading file {file_path}: {e}")
                return {"file_path": file_path, "error": str(e)}

        if not content:
            return {
                "file_path": file_path,
                "lines": 0,
                "language": "unknown",
                "symbols": [],
                "imports": [],
            }

        # Calculate basic metrics
        lines = content.splitlines()
        line_count = len(lines)
        blank_lines = sum(1 for line in lines if not line.strip())
        code_lines = line_count - blank_lines

        # Get language key
        ext_dot = get_file_ext(file_path)
        ext = ext_dot.lstrip(".")
        lang_key = parser_registry.get_language_key(ext) or ext

        # Check if language is supported
        parser_info = parser_registry.get_parser(ext)
        if not parser_info:
            return {
                "file_path": file_path,
                "lines": line_count,
                "language": lang_key,
                "symbols": [],
                "imports": [],
                "metrics": {
                    "total_lines": line_count,
                    "code_lines": code_lines,
                    "blank_lines": blank_lines,
                },
            }

        # Use TreeSitterExtractor for actual extraction
        # Run async method synchronously
        import asyncio
        try:
            result = asyncio.run(self._extractor.extract(file_path, content))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"TreeSitter extraction failed for {file_path}: {e}")
            result = None

        # Convert ExtractionResult to analysis dict
        symbols = []
        imports = []

        if result:
            # Extract symbols from entities
            for entity in result.entities:
                symbols.append({
                    "name": entity.name,
                    "type": entity.type,
                    "line": entity.start_line,
                })

            # Extract imports from relations
            for relation in result.relations:
                if relation.type in ("imports", "requires", "uses"):
                    imports.append(relation.target)

        return {
            "file_path": file_path,
            "language": lang_key,
            "metrics": {
                "total_lines": line_count,
                "code_lines": code_lines,
                "blank_lines": blank_lines,
            },
            "symbols": symbols,
            "imports": list(set(imports)),  # Unique imports
        }


# Global Instance
code_analyzer = CodeAnalyzer()
