import logging
import os
from threading import Lock

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
        # Mapping: thread_id -> temporary project_id (for Scheme C)
        self._thread_temp_projects: dict[str, int] = {}
        # Legacy compatibility for plugins
        self._default_root = None

        logger.info("ThreadContextStore initialized.")

    @property
    def default_root(self) -> str:
        """
        Get the default root directory.
        Lazily attempts to load from DB, falling back to settings or home dir.
        """
        # 优先从数据库获取（通过 SystemConfigService）
        db_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        if db_root:
            return os.path.abspath(db_root)

        # 最终回退：用户主目录
        return os.path.expanduser("~")

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
        # Note: project_id can be 0 (global mode), so use 'is not None' check
        if project_id is not None:
            self._thread_projects[thread_id] = project_id

    def get_working_directory(self, thread_id: str) -> str:
        """Get the working directory for a specific thread. Returns default if not set."""
        path = self._thread_contexts.get(thread_id)
        if path:
            return path
        return self.default_root

    def get_active_project(self, thread_id: str) -> int | None:
        """Get the active project ID for a specific thread."""
        # First check for temporary project (Scheme C)
        temp_project = self._thread_temp_projects.get(thread_id)
        if temp_project is not None:
            return temp_project
        return self._thread_projects.get(thread_id)

    def set_temp_project(self, thread_id: str, project_id: int | None):
        """Set or clear the temporary project ID for a specific thread (Scheme C)."""
        if project_id is not None:
            self._thread_temp_projects[thread_id] = project_id
            logger.info(f"Set temporary project {project_id} for thread {thread_id}")
        else:
            self._thread_temp_projects.pop(thread_id, None)
            logger.info(f"Cleared temporary project for thread {thread_id}")

    def get_temp_project(self, thread_id: str) -> int | None:
        """Get the temporary project ID for a specific thread."""
        return self._thread_temp_projects.get(thread_id)

    def clear_context(self, thread_id: str):
        """Remove context for a thread."""
        if thread_id in self._thread_contexts:
            del self._thread_contexts[thread_id]
        if thread_id in self._thread_projects:
            del self._thread_projects[thread_id]
        logger.info(f"Cleared context for thread {thread_id}")


# Global instance
thread_context_store = ThreadContextStore()
