"""
Code Exploration Engine - LSP-backed diagnostics for file edits.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CodeExplorationEngine:
    """
    LSP-backed type checker for file edits.
    """

    def __init__(self):
        from app.infrastructure.solidlsp.manager import LSPManager

        self.lsp_manager = LSPManager.get_instance()

    async def check_types(
        self, file_path: str, repo_path: str | None = None
    ) -> list[dict[str, Any]]:
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
            logger.exception(f"[Engine] Type check failed: {e}")
            return [{"error": str(e)}]

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
            formatted.append(
                {
                    "severity": d.get("severity"),
                    "message": d.get("message"),
                    "range": d.get("range"),
                    "source": d.get("source", "lsp"),
                }
            )
        return formatted


# Singleton getter
_engine: CodeExplorationEngine | None = None


def get_exploration_engine() -> CodeExplorationEngine:
    global _engine
    if _engine is None:
        _engine = CodeExplorationEngine()
    return _engine
