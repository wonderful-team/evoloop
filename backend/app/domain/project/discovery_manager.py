import logging
import os

from app.domain.watchers import ProjectDiscoveryWatcher
from app.domain.project.sync_service import project_sync_service

logger = logging.getLogger(__name__)


class ProjectDiscoveryManager:
    """
    Manages the project discovery watcher lifecycle.
    Handles WORKSPACE_ROOT changes and provides a clean interface for main.py.
    """

    def __init__(self):
        self._watcher: ProjectDiscoveryWatcher | None = None
        self._current_root: str | None = None

    def start(self, root_path: str) -> bool:
        """Start watching the given root path. Returns True if successful."""
        if not root_path or not os.path.exists(root_path):
            logger.warning(f"[DiscoveryManager] Invalid root path: {root_path}")
            return False

        # Normalize path
        root_path = os.path.abspath(root_path)

        # Stop existing watcher if path changed
        if self._watcher and self._current_root != root_path:
            logger.info(f"[DiscoveryManager] Root path changed, stopping old watcher")
            self.stop()

        # Start new watcher if not already watching this path
        if self._current_root != root_path:
            self._watcher = ProjectDiscoveryWatcher(root_path)
            self._watcher.start()
            self._current_root = root_path
            logger.info(f"[DiscoveryManager] Started watching: {root_path}")

        return True

    def stop(self):
        """Stop the current watcher."""
        if self._watcher:
            self._watcher.stop()
            logger.info(f"[DiscoveryManager] Stopped watching: {self._current_root}")
            self._watcher = None
            self._current_root = None

    async def switch_root(self, new_root: str) -> bool:
        """Switch to a new root path. Triggers reconciliation on success."""
        if not new_root or not os.path.exists(new_root):
            logger.warning(f"[DiscoveryManager] Cannot switch to invalid root: {new_root}")
            return False

        new_root = os.path.abspath(new_root)

        # Stop old watcher
        self.stop()

        # Start new watcher
        self._watcher = ProjectDiscoveryWatcher(new_root)
        self._watcher.start()
        self._current_root = new_root

        # Trigger reconciliation
        try:
            logger.info(f"[DiscoveryManager] Triggering reconciliation for: {new_root}")
            await project_sync_service.reconcile_projects(new_root)
        except Exception as e:
            logger.error(f"[DiscoveryManager] Reconciliation failed: {e}")

        return True

    @property
    def current_root(self) -> str | None:
        return self._current_root

    @property
    def is_watching(self) -> bool:
        return self._watcher is not None


# Global instance for application-wide use
discovery_manager = ProjectDiscoveryManager()
