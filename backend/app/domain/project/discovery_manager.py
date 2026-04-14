import logging
import os

from app.core.config import settings
from app.domain.project.sync_service import project_sync_service
from app.domain.watchers import ProjectDiscoveryWatcher
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)

# Config key for project discovery enable/disable
PROJECT_DISCOVERY_CONFIG_KEY = "PROJECT_DISCOVERY_ENABLED"


class ProjectDiscoveryManager:
    """
    Manages the project discovery watcher lifecycle.
    Handles WORKSPACE_ROOT changes and provides a clean interface for main.py.
    
    Project discovery can be disabled via:
    1. Environment variable: ENABLE_PROJECT_DISCOVERY=false
    2. System config: PROJECT_DISCOVERY_ENABLED=false (stored in database)
    """

    def __init__(self):
        self._watcher: ProjectDiscoveryWatcher | None = None
        self._current_root: str | None = None

    def _is_discovery_enabled(self) -> bool:
        """
        Check if project discovery is enabled.
        Priority: Environment Variable > System Config > Default (True)
        """
        # First check environment variable (for deployment/development override)
        if not settings.ENABLE_PROJECT_DISCOVERY:
            return False
        
        # Then check system config (for runtime user control)
        config_value = SystemConfigService.get_value(PROJECT_DISCOVERY_CONFIG_KEY)
        if config_value is not None:
            return config_value.lower() in ("true", "1", "yes", "on")
        
        # Default: enabled
        return True

    def start(self, root_path: str) -> bool:
        """Start watching the given root path. Returns True if successful."""
        if not root_path or not os.path.exists(root_path):
            logger.warning(f"[DiscoveryManager] Invalid root path: {root_path}")
            return False

        # Check if discovery is enabled
        if not self._is_discovery_enabled():
            logger.info(f"[DiscoveryManager] Project discovery is disabled. Skipping watcher start.")
            # Still track the root path for when discovery is re-enabled
            self._current_root = os.path.abspath(root_path)
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

        # Check if discovery is enabled before starting new watcher
        if not self._is_discovery_enabled():
            logger.info(f"[DiscoveryManager] Project discovery is disabled. Only updating root path.")
            self._current_root = new_root
            # Still trigger reconciliation to sync existing projects
            try:
                logger.info(f"[DiscoveryManager] Triggering reconciliation for: {new_root}")
                await project_sync_service.reconcile_projects(new_root)
            except Exception as e:
                logger.error(f"[DiscoveryManager] Reconciliation failed: {e}")
            return True

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

    @property
    def is_discovery_enabled(self) -> bool:
        """Check if project discovery is currently enabled."""
        return self._is_discovery_enabled()

    async def set_discovery_enabled(self, enabled: bool) -> bool:
        """
        Enable or disable project discovery dynamically.
        
        Args:
            enabled: True to enable discovery, False to disable
            
        Returns:
            True if the operation was successful
        """
        was_enabled = self._is_discovery_enabled()
        new_value = "true" if enabled else "false"
        
        # Update system config
        SystemConfigService.set_value(
            PROJECT_DISCOVERY_CONFIG_KEY, 
            new_value,
            description="Enable or disable automatic project discovery in workspace"
        )
        
        logger.info(f"[DiscoveryManager] Project discovery {'enabled' if enabled else 'disabled'}")
        
        # Handle watcher state change
        if enabled and not was_enabled:
            # Discovery was just enabled - start watcher if we have a root
            if self._current_root and os.path.exists(self._current_root):
                logger.info(f"[DiscoveryManager] Starting watcher after discovery enabled")
                self._watcher = ProjectDiscoveryWatcher(self._current_root)
                self._watcher.start()
                return True
        elif not enabled and was_enabled:
            # Discovery was just disabled - stop watcher
            if self._watcher:
                logger.info(f"[DiscoveryManager] Stopping watcher after discovery disabled")
                self.stop()
        
        return True

    async def on_config_changed(self, old_value: str, new_value: str):
        """
        Handler for configuration changes.
        Called when PROJECT_DISCOVERY_ENABLED config is updated.
        """
        logger.info(f"[DiscoveryManager] Config changed: {old_value} -> {new_value}")
        enabled = new_value.lower() in ("true", "1", "yes", "on")
        await self.set_discovery_enabled(enabled)


# Global instance for application-wide use
discovery_manager = ProjectDiscoveryManager()

# Register config change handler
SystemConfigService.register_change_handler(
    PROJECT_DISCOVERY_CONFIG_KEY, 
    discovery_manager.on_config_changed
)
