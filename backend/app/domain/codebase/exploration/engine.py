"""
Code Exploration Engine - Automatic Backend Selection

Intelligently chooses between Knowledge Graph, LSP, and unified Search Center
based on data availability and query characteristics.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.file import FileSearcher

logger = logging.getLogger(__name__)


class CodeExplorationEngine:
    """
    Unified code exploration with automatic backend selection.

    Backend priority:
    1. Knowledge Graph (fastest, pre-indexed)
    2. LSP (real-time, language-aware)
    3. Search Center (fallback, always available)
    """

    def __init__(self):
        from app.infrastructure.solidlsp.manager import LSPManager

        self.lsp_manager = LSPManager.get_instance()

    async def find_symbol(
        self,
        name: str,
        project_id: int = DEFAULT_PROJECT_ID,
        repo_path: str | None = None,
    ) -> dict | None:
        """
        Find symbol definition using SQL retrieval, with grep fallback.
        """
        from app.domain.codebase.retrieval.service import RetrievalService

        retriever = RetrievalService()
        try:
            results = await retriever.find_symbol_definition(name, project_id)
            if results:
                logger.info(f"[Engine] Found '{name}' via SQL retrieval")
                return {
                    "source": "sql",
                    "results": results
                }
        except Exception as e:
            logger.debug(f"[Engine] SQL lookup failed: {e}")

        try:
            results = await self._grep_find_symbol(name, repo_path)
            if results:
                logger.info(f"[Engine] Found '{name}' via Search Center fallback")
                return {
                    "source": "search_center",
                    "results": results
                }
        except Exception as e:
            logger.debug(f"[Engine] Search center lookup failed: {e}")

        return None

    async def search_code(
        self,
        pattern: str,
        scope: str | None = None,
        repo_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Search code using unified FileSearcher."""
        if not repo_path:
            from app.core.tools import get_working_directory

            repo_path = get_working_directory(None)

        results = await FileSearcher.search_content(pattern, repo_path, scope=scope)

        return [
            {
                "file_path": r["file"],
                "line": r["line"],
                "content": r["content"]
            } for r in results
        ]

    async def _grep_find_symbol(self, name: str, repo_path: str | None) -> list[dict[str, Any]]:
        """Use unified FileSearcher to find symbol definition."""
        if not repo_path:
            from app.core.tools import get_working_directory

            repo_path = get_working_directory(None)

        # Pattern to match class/function definitions across common languages
        pattern = f"(class|def|interface|function|struct|type)\\s+{re.escape(name)}\\b"

        results = await FileSearcher.search_content(pattern, repo_path, limit=10)

        return [{
            "file_path": r["file"],
            "line": r["line"],
            "content": r["content"]
        } for r in results]

    async def check_types(self, file_path: str, repo_path: str | None = None) -> list[dict[str, Any]]:
        """Check for type errors using LSP."""
        if not repo_path:
            repo_path = str(Path(file_path).parent)

        suffix = Path(file_path).suffix.lower()
        language = self._get_language_from_suffix(suffix)

        if not language:
            return [{"error": f"Unsupported language for type checking: {suffix}"}]

        try:
            server = self.lsp_manager.get_server(language, repo_path)
            relative_path = str(Path(file_path).relative_to(repo_path))

            # Wait for diagnostics
            diagnostics = []
            for _ in range(20):  # Wait up to 2 seconds
                raw = server.get_diagnostics(relative_path)
                if raw:
                    diagnostics = raw
                    break
                await asyncio.sleep(0.1)

            return self._format_diagnostics(diagnostics)

        except Exception as e:
            logger.error(f"[Engine] Type check failed: {e}")
            return [{"error": str(e)}]

    async def analyze_impact(self, symbol: str, project_id: int = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        """Analyze symbol impact using SQL retrieval."""
        from app.domain.codebase.retrieval.service import RetrievalService

        retriever = RetrievalService()
        try:
            usages = await retriever.find_usages(symbol, project_id)
            return usages or []
        except Exception as e:
            logger.error(f"[Engine] Impact analysis failed: {e}")
            return []

    def _get_language_from_suffix(self, suffix: str) -> str | None:
        """Map file suffix to language name."""
        mapping = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "typescript",
            ".jsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c++",
            ".cpp": "c++",
            ".h": "c++",
            ".php": "php",
            ".vue": "vue",
        }
        return mapping.get(suffix.lower())

    def _format_diagnostics(self, diagnostics: list) -> list[dict[str, Any]]:
        """Format LSP diagnostics for engine output."""
        formatted = []
        for d in diagnostics:
            formatted.append({
                "severity": d.get("severity"),
                "message": d.get("message"),
                "range": d.get("range"),
                "source": d.get("source", "lsp")
            })
        return formatted


# Singleton getter
_engine: CodeExplorationEngine | None = None


def get_exploration_engine() -> CodeExplorationEngine:
    global _engine
    if _engine is None:
        _engine = CodeExplorationEngine()
    return _engine
