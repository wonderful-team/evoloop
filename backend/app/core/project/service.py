import logging
import os
import time
from threading import Lock

from app.core.context.plugins import set_workspace_provider

logger = logging.getLogger(__name__)


class ProjectContextManager:
    """
    Manages the working directory context for different threads (sessions).
    This allows the server to support multiple active projects simultaneously.
    Integrates with EvoCloud API for project discovery.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        # Project Structure Cache
        # Mapping: working_dir -> { "structure": str, "timestamp": float }
        self._structure_cache: dict[str, dict] = {}

        logger.info("ProjectContextManager initialized as the WorkspaceProvider")

    async def get_project_structure(self, path: str, force_refresh: bool = False) -> str:
        """
        Get the annotated directory tree for a path. Uses caching.
        """
        if not force_refresh and path in self._structure_cache:
            logger.debug(f"[ProjectContext] Cache hit for structure: {path}")
            return self._structure_cache[path]["structure"]

        from app.core.project.tree_generator import AnnotatedTreeGenerator

        logger.info(f"[ProjectContext] Generating structure for: {path}")
        # Standard constraints for Generalist Agent
        generator = AnnotatedTreeGenerator(
            path,
            max_depth=3,
            with_symbols=False,
            file_limit=30,
            max_lines=150 # Guard against extreme bloat
        )
        structure = await generator.generate()

        self._structure_cache[path] = {
            "structure": structure,
            "timestamp": time.time()
        }
        return structure

    def invalidate_cache(self, path: str | None = None):
        """Invalidate the structure cache for a path or all paths."""
        if path:
            if path in self._structure_cache:
                del self._structure_cache[path]
                logger.info(f"[ProjectContext] Invalidated cache for: {path}")
        else:
            self._structure_cache.clear()
            logger.info("[ProjectContext] Invalidated all structure caches")

    def extract_description_from_readme(self, project_path: str) -> str:
        """
        Helper to find and read the README file from a project path.
        Returns empty string if not found or unreadable.
        """
        if not project_path or not os.path.exists(project_path):
            return ""

        candidates = ["README.md", "readme.md", "README.txt", "readme.txt", "README"]
        for c in candidates:
            full_path = os.path.join(project_path, c)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                try:
                    from app.core.file import read_file
                    return read_file(full_path).content
                except Exception as e:
                    logger.warning(f"Failed to read README at {full_path}: {e}")
                    continue
        return ""


# Global instance
project_context_manager = ProjectContextManager()

set_workspace_provider(project_context_manager)
