import logging
from typing import Any, Dict, List

from app.utils.process import run_async_command

from .filter import get_grep_exclude_args, get_ripgrep_exclude_args

logger = logging.getLogger(__name__)

class FileSearcher:
    """
    Unified search engine wrapper for the file system.
    Handles grep/ripgrep orchestration and output parsing.
    """

    @staticmethod
    def _has_ripgrep() -> bool:
        import shutil
        return shutil.which("rg") is not None

    @staticmethod
    async def search_content(
        pattern: str,
        root_path: str,
        scope: str | None = None,
        case_insensitive: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search for text patterns inside files.
        """
        if FileSearcher._has_ripgrep():
            cmd = ["rg", "-n", "--json"]
            if case_insensitive:
                cmd.append("-i")
            if scope:
                cmd.extend(["-g", scope])
            cmd.extend(get_ripgrep_exclude_args())
            cmd.append(pattern)
            cmd.append(root_path)
        else:
            cmd = ["grep", "-r", "-i", "-n", "-I"]
            if not case_insensitive:
                cmd.remove("-i")
            if scope:
                cmd.extend(["--include", scope])
            cmd.extend(get_grep_exclude_args())
            cmd.append(pattern)
            cmd.append(root_path)

        result = await run_async_command(cmd)
        if not result.stdout:
            return []

        # Parse output (simplified for now, mimicking existing logic)
        results = []
        lines = result.stdout.strip().split('\n')
        for line in lines[:limit]:
            try:
                if line.startswith("{"):
                    import json
                    data = json.loads(line)
                    if data.get("type") == "match":
                        results.append({
                            "file": data["data"]["path"]["text"],
                            "line": data["data"]["line_number"],
                            "content": data["data"]["lines"]["text"].strip()
                        })
                else:
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        results.append({
                            "file": parts[0],
                            "line": int(parts[1]),
                            "content": parts[2].strip()
                        })
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                continue
        return results
