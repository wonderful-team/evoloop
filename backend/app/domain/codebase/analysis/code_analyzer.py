"""
Code Analyzer Module
Ported from Legacy `CodeSymbolExtractor`.
Provides deep analysis of code files using Tree-sitter.
"""
import logging
from typing import Any

from app.domain.codebase.indexing.parsers import parser_registry
from app.domain.codebase.indexing.queries import TREE_SITTER_QUERIES

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """
    Code Analyzer using Tree-sitter.
    Extracts structure, metrics, and symbols.
    """

    def __init__(self):
        # Parsers logic moved to ParserRegistry
        pass

    def analyze_file(self, file_path: str, content: str = None) -> dict[str, Any]:
        """
        Analyze a file and return structural info and metrics.
        """
        if content is None:
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")
                return {}

        if not content:
            return {}

        ext = file_path.split(".")[-1].lower()

        parser_info = parser_registry.get_parser(ext)
        if not parser_info:
            # Fallback for non-supported
            return {
                "file_path": file_path,
                "lines": len(content.splitlines()),
                "language": "unknown",
                "symbols": []
            }

        parser, language = parser_info
        tree = parser.parse(bytes(content, "utf8"))
        root = tree.root_node

        # Metrics
        lines = content.splitlines()
        line_count = len(lines)
        blank_lines = sum(1 for line in lines if not line.strip())
        code_lines = line_count - blank_lines
        complexity = 0 # Placeholder

        # Structure Extraction
        symbols = []
        imports = []

        lang_key = parser_registry.get_language_key(ext)

        if lang_key and lang_key in TREE_SITTER_QUERIES:
            q_map = TREE_SITTER_QUERIES[lang_key]

            # Extract Definitions
            defs_query = language.query(q_map["defs"])
            # import tree_sitter # Not needed for object methods in new bindings usually
            from tree_sitter import QueryCursor
            cursor = QueryCursor(defs_query)
            matches = cursor.matches(root)

            for _, captures in matches:
                # Logic to extract name and type
                # Simplified: Just grab the first capture
                for name, nodes in captures.items():
                    if isinstance(nodes, list):
                        node = nodes[0]
                    else:
                        node = nodes

                    if name in ["function", "class"]:
                        # Look for @name in the same match?
                        # Tree sitter matches returns dict.
                        # In the query: (func ... @func) (name ... @name)
                        # So both are in captures.

                        symbol_name = "anon"
                        if "name" in captures:
                            n_nodes = captures["name"]
                            n_node = n_nodes[0] if isinstance(n_nodes, list) else n_nodes
                            symbol_name = n_node.text.decode("utf8")

                        symbols.append({
                            "name": symbol_name,
                            "type": name,
                            "line": node.start_point[0] + 1
                        })

            # Extract Imports
            if "imports" in q_map:
                imp_query = language.query(q_map["imports"])
                cursor = QueryCursor(imp_query)
                matches = cursor.matches(root)
                for _, captures in matches:
                    if "module" in captures:
                        m_nodes = captures["module"]
                        m_node = m_nodes[0] if isinstance(m_nodes, list) else m_nodes
                        imports.append(m_node.text.decode("utf8").strip('"\''))

        return {
            "file_path": file_path,
            "language": lang_key or ext,
            "metrics": {
                "total_lines": line_count,
                "code_lines": code_lines,
                "blank_lines": blank_lines
                # "complexity": ... (Porting complexity logic is verbose, skipping for MVP)
            },
            "symbols": symbols,
            "imports": list(set(imports))  # Unique imports
        }


# Global Instance
code_analyzer = CodeAnalyzer()
