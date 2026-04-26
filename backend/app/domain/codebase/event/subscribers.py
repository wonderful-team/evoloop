"""
Codebase Domain Event Subscribers
==================================

Event subscribers for codebase indexing and cross-domain events.
"""

import asyncio
import logging
import os

from app.core.events.base import BaseEvent
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.domain.project.event import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectMovedEvent,
    ProjectEventType,
)

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
            root_projects_dir = SystemConfigService.get_value("WORKSPACE_ROOT")

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


@event_register()
class CodebaseSystemEventHandler:
    """
    Handles system-level events that affect the codebase domain.

    Subscribes to:
    - system.embedding_updated: Re-index when embedding model changes
    - project.switched: Setup context when user switches project
    """

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


@event_register()
class IndexingEventHandler:
    """
    Handles project events to trigger indexing operations.

    This handler bridges the project domain with the indexing domain,
    enabling loose coupling between these components.
    """

    @event_subscribe(ProjectEventType.PROJECT_CREATED)
    async def on_project_created(self, event: BaseEvent) -> None:
        """
        Handle project creation by starting file watching and indexing.
        """
        if not isinstance(event, ProjectCreatedEvent):
            return

        logger.info(f"[IndexingHandler] Received ProjectCreatedEvent for: {event.path}")

        try:
            from app.domain.codebase.indexing.manager import indexing_manager

            await indexing_manager.start_watching(event.path, event.repo_id)
            # Fire and forget - don't await background indexing
            asyncio.create_task(indexing_manager.run_indexing_background(event.repo_id))

            logger.info(f"[IndexingHandler] Started watching and indexing: {event.path}")
        except Exception as e:
            logger.error(f"[IndexingHandler] Failed to start indexing for {event.path}: {e}")

    @event_subscribe(ProjectEventType.PROJECT_DELETED)
    async def on_project_deleted(self, event: BaseEvent) -> None:
        """
        Handle project deletion by stopping file watching.
        """
        if not isinstance(event, ProjectDeletedEvent):
            return

        logger.info(f"[IndexingHandler] Received ProjectDeletedEvent for: {event.path}")

        try:
            from app.domain.codebase.indexing.manager import indexing_manager

            await indexing_manager.stop_watching(event.path)

            logger.info(f"[IndexingHandler] Stopped watching: {event.path}")
        except Exception as e:
            logger.error(f"[IndexingHandler] Failed to stop watching {event.path}: {e}")

    @event_subscribe(ProjectEventType.PROJECT_MOVED)
    async def on_project_moved(self, event: BaseEvent) -> None:
        """
        Handle project move/rename by updating watcher paths.
        """
        if not isinstance(event, ProjectMovedEvent):
            return

        logger.info(f"[IndexingHandler] Received ProjectMovedEvent: {event.src_path} -> {event.dest_path}")

        try:
            from app.domain.codebase.indexing.manager import indexing_manager

            # Stop old path
            await indexing_manager.stop_watching(event.src_path)
            # Start new path
            await indexing_manager.start_watching(event.dest_path, event.repo_id)

            logger.info(f"[IndexingHandler] Updated watcher: {event.src_path} -> {event.dest_path}")
        except Exception as e:
            logger.error(f"[IndexingHandler] Failed to handle move: {e}")
