"""
Code Exploration Engine - Automatic Backend Selection

Intelligently chooses between Knowledge Graph, LSP, and Grep
based on data availability and query characteristics.
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.memory import memory_manager
from app.utils.process import run_command
from app.constants import DEFAULT_EXCLUDED_DIRS

logger = logging.getLogger(__name__)


class CodeExplorationEngine:
    """
    Unified code exploration with automatic backend selection.
    
    Backend priority:
    1. Knowledge Graph (fastest, pre-indexed)
    2. LSP (real-time, language-aware)
    3. Grep (fallback, always available)
    """
    
    def __init__(self):
        from app.domain.tools.coding.lsp import LSPManager
        self.lsp_manager = LSPManager.get_instance()
    
    async def find_symbol(
        self,
        name: str,
        project_id: int = 1,
        repo_path: Optional[str] = None
    ) -> Optional[dict]:
        """
        Find symbol definition using best available backend.
        
        Priority:
        1. Knowledge Graph (O(1) lookup)
        2. LSP (if file is open)
        3. Grep (pattern matching fallback)
        """
        # 1. Try Knowledge Graph first
        try:
            from app.domain.codebase.retrieval.graph_service import graph_retrieval_service
            results = await graph_retrieval_service.find_symbol_definition(name, project_id)
            if results:
                logger.info(f"[Engine] Found '{name}' in Knowledge Graph")
                return {
                    "source": "graph",
                    "results": results
                }
        except Exception as e:
            logger.debug(f"[Engine] Graph lookup failed: {e}")
        
        # 2. Try LSP (if we can locate the file)
        if repo_path:
            try:
                # Guess file from symbol name (heuristic)
                file_paths = self._guess_file_paths(name, repo_path)
                for file_path in file_paths:
                    if Path(file_path).exists():
                        # Try to get LSP server for this file
                        suffix = Path(file_path).suffix.lower()
                        language = self._get_language_from_suffix(suffix)
                        if language:
                            try:
                                server = self.lsp_manager.get_server(language, repo_path)
                                # We'd need line/char to use LSP effectively
                                # For now, skip to grep for symbol search
                                break
                            except Exception:
                                continue
            except Exception as e:
                logger.debug(f"[Engine] LSP lookup failed: {e}")
        
        # 3. Fallback to Grep (always works)
        try:
            results = self._grep_find_symbol(name, repo_path)
            if results:
                logger.info(f"[Engine] Found '{name}' via Grep fallback")
                return {
                    "source": "grep",
                    "results": results
                }
        except Exception as e:
            logger.debug(f"[Engine] Grep lookup failed: {e}")
        
        return None
    
    async def search_code(
        self,
        pattern: str,
        scope: Optional[str] = None,
        repo_path: Optional[str] = None
    ) -> list[dict]:
        """
        Search code using Grep (primary) or Semantic search.
        """
        if not repo_path:
            from app.core.tools import get_working_directory
            repo_path = get_working_directory(None)
        
        # Use ripgrep if available, fallback to grep
        cmd = ["rg", "-n", "--json", pattern] if self._has_ripgrep() else ["grep", "-rn", pattern]
        
        if scope:
            if cmd[0] == "rg":
                cmd.extend(["-g", scope])
            else:
                cmd.extend(["--include", scope])
        
        for exclude_dir in DEFAULT_EXCLUDED_DIRS:
            if cmd[0] == "rg":
                cmd.extend(["-g", f"!{exclude_dir}"])
            else:
                cmd.extend([f"--exclude-dir={exclude_dir}"])
        
        cmd.append(repo_path)
        
        try:
            res = run_command(cmd)
            if res.success and res.stdout:
                return self._parse_search_results(res.stdout)
        except Exception as e:
            logger.error(f"[Engine] Search failed: {e}")
        
        return []
    
    async def check_types(
        self,
        file_path: str,
        repo_path: Optional[str] = None
    ) -> list[dict]:
        """
        Check for type errors using LSP.
        """
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
            import asyncio
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
    
    async def analyze_impact(
        self,
        symbol: str,
        project_id: int = 1
    ) -> list[dict]:
        """
        Analyze symbol impact using Knowledge Graph.
        """
        try:
            from app.domain.codebase.retrieval.graph_service import graph_retrieval_service
            usages = await graph_retrieval_service.find_usages(symbol, project_id)
            return usages or []
        except Exception as e:
            logger.error(f"[Engine] Impact analysis failed: {e}")
            return []
    
    def _guess_file_paths(self, symbol_name: str, repo_path: str) -> list[str]:
        """Heuristic to guess file paths from symbol name."""
        paths = []
        # Common patterns: UserService -> user_service.py, UserService.ts, etc.
        snake_name = self._to_snake_case(symbol_name)
        for ext in [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java"]:
            paths.append(str(Path(repo_path) / f"{snake_name}{ext}"))
        return paths
    
    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def _get_language_from_suffix(self, suffix: str) -> Optional[str]:
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
    
    def _grep_find_symbol(self, name: str, repo_path: Optional[str]) -> list[dict]:
        """Use grep to find symbol definition."""
        if not repo_path:
            from app.core.tools import get_working_directory
            repo_path = get_working_directory(None)
        
        # Pattern to match class/function definitions
        import re
        cmd = ["grep", "-rnE", f"(class|def|interface|function|struct|type)\\s+{re.escape(name)}\\b", repo_path]
        
        for exclude_dir in DEFAULT_EXCLUDED_DIRS:
            cmd.extend([f"--exclude-dir={exclude_dir}"])
        
        res = run_command(cmd)
        if res.success and res.stdout:
            results = []
            for line in res.stdout.strip().split("\n")[:10]:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    results.append({
                        "file_path": parts[0],
                        "line": int(parts[1]),
                        "content": parts[2].strip()
                    })
            return results
        return []
    
    def _has_ripgrep(self) -> bool:
        """Check if ripgrep is available."""
        try:
            import shutil
            return shutil.which("rg") is not None
        except Exception:
            return False
    
    def _parse_search_results(self, stdout: str) -> list[dict]:
        """Parse grep/ripgrep output."""
        results = []
        for line in stdout.strip().split("\n")[:20]:
            if not line:
                continue
            try:
                # Handle ripgrep JSON format
                if line.startswith("{"):
                    import json
                    data = json.loads(line)
                    if data.get("type") == "match":
                        path = data["data"]["path"]["text"]
                        line_num = data["data"]["line_number"]
                        text = data["data"]["lines"]["text"].strip()
                        results.append({
                            "file_path": path,
                            "line": line_num,
                            "content": text
                        })
                else:
                    # Standard grep format: file:line:content
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        results.append({
                            "file_path": parts[0],
                            "line": int(parts[1]),
                            "content": parts[2].strip()
                        })
            except Exception:
                continue
        return results
    
    def _format_diagnostics(self, raw_diagnostics: list) -> list[dict]:
        """Format LSP diagnostics."""
        severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
        results = []
        for d in raw_diagnostics:
            rng = d.get("range", {})
            start = rng.get("start", {})
            results.append({
                "line": start.get("line", -1) + 1,
                "column": start.get("character", -1) + 1,
                "severity": severity_map.get(d.get("severity", 1), "Error"),
                "message": d.get("message", "No message"),
                "source": d.get("source", "LSP"),
            })
        return results


# Global instance
_exploration_engine: Optional[CodeExplorationEngine] = None


def get_exploration_engine() -> CodeExplorationEngine:
    """Get or create the global exploration engine."""
    global _exploration_engine
    if _exploration_engine is None:
        _exploration_engine = CodeExplorationEngine()
    return _exploration_engine
