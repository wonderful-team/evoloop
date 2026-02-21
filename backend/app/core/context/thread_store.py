import logging
import os
from threading import Lock

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class ThreadContextStore:
    """
    Manages the working directory context and active project IDs for different threads (sessions).
    This allows the server to support multiple active projects simultaneously.
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
        # Mapping: thread_id -> working_directory path
        self._thread_contexts: dict[str, str] = {}
        # Mapping: thread_id -> project_id
        self._thread_projects: dict[str, int] = {}

        # Default fallback directory (from Settings/DB)
        db_root = SystemConfigService.get_value("PROJECTS_ROOT")
        self._default_root = os.path.abspath(db_root if db_root else settings.PROJECTS_ROOT)
        logger.info(f"ThreadContextStore initialized. Default root: {self._default_root}")

    def set_working_directory(self, thread_id: str, path: str):
        """Set the working directory for a specific thread."""
        if not path:
            logger.warning(f"Attempted to set empty path for thread {thread_id}")
            return

        # With API-driven projects, the path might be on a remote server (conceptually)
        # But for EvoLoop to work, it must be mounted/present locally at 'path'.
        # We assume 'external_path' from API maps to a valid local path.
        if not os.path.exists(path):
            logger.warning(f"Setting working directory to non-existent path: {path}. Agent actions might fail.")

        self._thread_contexts[thread_id] = path
        logger.info(f"Updated working directory for thread {thread_id} -> {path}")

    def set_active_project(self, thread_id: str, project_id: int):
        """Set the active project ID for a specific thread."""
        if project_id:
            self._thread_projects[thread_id] = project_id

    def get_working_directory(self, thread_id: str) -> str:
        """Get the working directory for a specific thread. Returns default if not set."""
        path = self._thread_contexts.get(thread_id)
        if path:
            return path
        return self._default_root

    def get_active_project(self, thread_id: str) -> int | None:
        """Get the active project ID for a specific thread."""
        return self._thread_projects.get(thread_id)

    def clear_context(self, thread_id: str):
        """Remove context for a thread."""
        if thread_id in self._thread_contexts:
            del self._thread_contexts[thread_id]
        if thread_id in self._thread_projects:
            del self._thread_projects[thread_id]
        logger.info(f"Cleared context for thread {thread_id}")


# Global instance
thread_context_store = ThreadContextStore()
