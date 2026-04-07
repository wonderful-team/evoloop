"""
Codebase Domain Event Handlers

Handles cross-domain system events for the codebase domain.
Uses @event_register and @event_subscribe decorators for automatic registration.
"""

import asyncio
import logging
import os

from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe
from app.domain.project.events import ProjectEventType

logger = logging.getLogger(__name__)


@event_register()
class CodebaseSystemEventHandler:
    """
    Handles system-level events that affect the codebase domain.
    
    Subscribes to:
    - system.embedding_updated: Re-index when embedding model changes
    - project.switched: Setup context when user switches project
    """

    def __init__(self):
        pass

    @event_subscribe("system.embedding_updated")
    async def on_embedding_updated(self, event: BaseEvent) -> None:
        """
        Handle embedding model update by triggering background re-index.
        """
        repo_id = event.data.get("repo_id")
        if repo_id:
            logger.info(f"[Codebase] Received embedding_updated event. Triggering background re-index for repo {repo_id}")
            from app.domain.codebase.indexing.manager import indexing_manager
            # Run in background without awaiting the entire indexing process to block the event bus
            asyncio.create_task(indexing_manager.run_indexing_background(repo_id))

    @event_subscribe(ProjectEventType.PROJECT_SWITCHED)
    async def on_project_switched(self, event: BaseEvent) -> None:
        """
        Handle project switch by restoring watchers and index state.
        """
        project_id = event.data.get("project_id")
        path = event.data.get("path")
        if path and project_id:
            logger.info(f"[Codebase] Received project.switched event. Restoring watchers and index state for {path}")
            try:
                from app.domain.codebase.indexing.manager import indexing_manager
                from app.domain.codebase.indexing.service import IndexingService

                service = IndexingService()
                repo_name = os.path.basename(path)
                repo = await service.get_or_create_repo(path, repo_name, project_id=project_id)
                await indexing_manager.start_watching(path, repo.id)

                # Trigger Smart Full-Indexing for "Staleness Check"
                asyncio.create_task(indexing_manager.run_indexing_background(repo.id))
            except Exception as e:
                logger.error(f"[Codebase] Failed to handle project switch for {path}: {e}")


def register_codebase_events():
    """
    Register codebase domain listeners.
    
    Note: With @event_register() decorator, handlers are auto-registered on import.
    This function is kept for explicit registration if needed.
    """
    CodebaseSystemEventHandler()
    logger.info("📡 Codebase system event handlers registered")
