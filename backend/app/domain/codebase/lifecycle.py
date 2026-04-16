"""
Codebase Domain Lifecycle Handlers
Handles application-level startup and shutdown events for indexing.
"""
import logging
import os
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class IndexingLifecycleHandler:
    """
    Handles application-level lifecycle events for the Codebase domain.
    
    Includes:
    - Auto-starting watchers for the active project on app start
    - Graceful shutdown of indexing tasks and file watchers on app stop
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Start indexing for the active project if detected.
        """
        try:
            from app.core.context import thread_context_store
            from app.core.config import settings
            from app.infrastructure.config import SystemConfigService
            from app.domain.codebase.indexing.manager import indexing_manager
            from app.domain.codebase.indexing.service import IndexingService

            default_path = thread_context_store.get_working_directory("default")
            
            # Get workspace root to avoid indexing the entire root as one repo
            db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            root_projects_dir = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT

            if default_path and os.path.exists(default_path):
                # Ensure it's not the root itself
                if root_projects_dir and os.path.abspath(default_path) == os.path.abspath(root_projects_dir):
                    logger.debug("[Indexing] Active path is root, skipping auto-indexing.")
                    return

                service = IndexingService()
                repo_name = os.path.basename(default_path)
                repo = await service.get_or_create_repo(default_path, repo_name)
                await indexing_manager.start_watching(default_path, repo.id)
                logger.info(f"[Indexing] ✓ Active project indexing started: {default_path}")
        except Exception as e:
            logger.warning(f"[Indexing] Failed to start active project indexing: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING: Stop all codebase indexing activities."""
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.stop_all()
            logger.info("[Indexing] All indexing watchers and tasks stopped")
        except Exception as e:
            logger.warning(f"[Indexing] Failed to stop indexing manager: {e}")
