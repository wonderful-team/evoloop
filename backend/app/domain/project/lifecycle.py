"""
Project Module Lifecycle Handlers
Handles application-level startup, shutdown, and system-wide signals for projects.
"""
import logging
import os

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class ProjectLifecycleHandler:
    """
    Handles initialization and cleanup of project management infrastructure.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Initialize project discovery and reconcile state.
        """
        from app.core.config import settings
        from app.infrastructure.config import SystemConfigService
        from app.domain.project.discovery_manager import discovery_manager
        
        root_projects_dir = SystemConfigService.get_value("WORKSPACE_ROOT")
        if not root_projects_dir:
            logger.warning("[Project] WORKSPACE_ROOT not configured. Skipping discovery.")
            return
            
        if not os.path.exists(root_projects_dir):
            logger.warning(f"[Project] WORKSPACE_ROOT '{root_projects_dir}' does not exist.")
            return

        try:
            # 1. Start Manager
            discovery_manager.start(root_projects_dir)
            
            # 2. Reconcile (Sync filesystem with DB)
            from app.domain.project.sync_service import project_sync_service
            logger.info(f"[Project] Synchronizing projects in {root_projects_dir}...")
            await project_sync_service.reconcile_projects(root_projects_dir)
            logger.info("[Project] ✓ Discovery and synchronization complete")
        except Exception as e:
            logger.error(f"[Project] Startup initialization failed: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING: Stop project discovery manager."""
        try:
            from app.domain.project.discovery_manager import discovery_manager
            discovery_manager.stop()
            logger.info("[Project] Project discovery manager stopped")
        except Exception as e:
            logger.warning(f"[Project] Failed to stop discovery manager: {e}")

    @event_subscribe(SystemEventType.CONTEXT_POLISHING)
    async def on_context_polishing(self, event):
        """Handle system-wide context polishing request."""
        try:
            from app.domain.project.polisher import project_polisher
            await project_polisher.handle_context_polishing(event)
        except Exception as e:
            logger.error(f"[Project] Context polishing failed: {e}")

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")

        if key == "WORKSPACE_ROOT":
            if not new_value or not os.path.exists(new_value):
                logger.warning(f"[Project] New WORKSPACE_ROOT '{new_value}' is invalid or does not exist.")
                return

            try:
                from app.domain.project.sync_service import project_sync_service
                logger.info(f"[Project] WORKSPACE_ROOT changed, reconciling projects in {new_value}...")
                await project_sync_service.reconcile_projects(new_value)
                
                # Restart discovery manager for new path
                from app.domain.project.discovery_manager import discovery_manager
                discovery_manager.stop()
                discovery_manager.start(new_value)
                logger.info(f"[Project] Discovery manager restarted for {new_value}")
                
            except Exception as e:
                logger.error(f"[Project] Failed to handle WORKSPACE_ROOT change: {e}")
