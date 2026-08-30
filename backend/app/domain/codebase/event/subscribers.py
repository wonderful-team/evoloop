"""
Codebase Domain Event Subscribers
==================================

Event subscribers for codebase indexing and cross-domain events.
"""

import asyncio
import logging
import os

from app.core.events import SystemEventType
from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.project.event import (
    ProjectCreatedEvent,
    ProjectDeletedEvent,
    ProjectEventType,
    ProjectMovedEvent,
)
from app.domain.codebase.constants import (
    GENERATION_ITEM_APPMAP,
    GENERATION_ITEM_SUMMARY,
    GENERATION_ITEM_WIKI,
)
from app.domain.codebase.event.types import IndexingEventType

logger = logging.getLogger(__name__)


@event_register()
class IndexingLifecycleSubscriber:
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
            from app.domain.codebase.indexing.manager import indexing_manager
            from app.domain.codebase.indexing.service import IndexingService

            default_path = thread_context_store.get_working_directory("default")

            # Prefer resolving via active project_id to avoid watching WORKSPACE_ROOT
            active_project_id = thread_context_store.get_active_project("default")
            if active_project_id:
                from app.core.project.utils import get_project_path

                resolved_path = await get_project_path(active_project_id)
                if resolved_path and os.path.isdir(resolved_path):
                    default_path = resolved_path

            # Get workspace root to avoid indexing the entire root as one repo
            from app.core.project.utils import get_workspace_root

            root_projects_dir = get_workspace_root()

            if default_path and os.path.exists(default_path):
                # Ensure it's not the root itself
                if root_projects_dir and os.path.abspath(
                    default_path
                ) == os.path.abspath(root_projects_dir):
                    logger.debug(
                        "[Indexing] Active path is root, skipping auto-indexing."
                    )
                    return

                service = IndexingService()
                repo_name = os.path.basename(default_path)
                repo = await service.get_or_create_repo(default_path, repo_name)
                await indexing_manager.start_watching(default_path, repo.id)
                logger.info(
                    f"[Indexing] ✓ Active project indexing started: {default_path}"
                )
        except Exception as e:
            logger.warning(
                f"[Indexing] Failed to start active project indexing: {e}",
                exc_info=True,
            )

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING: Stop all codebase indexing activities."""
        try:
            from app.domain.codebase.indexing.manager import indexing_manager

            await indexing_manager.stop_all()
            logger.info("[Indexing] All indexing watchers and tasks stopped")
        except Exception as e:
            logger.warning(
                f"[Indexing] Failed to stop indexing manager: {e}", exc_info=True
            )


@event_register()
class CodebaseSystemEventSubscriber:
    """
    Handles system-level events that affect the codebase domain.

    Subscribes to:
    - system.embedding_updated: Re-index when embedding model changes
    - project.switched: Setup context when user switches project
    """

    @event_subscribe(SystemEventType.EMBEDDING_UPDATED)
    async def on_embedding_updated(self, event: BaseEvent) -> None:
        """
        Handle embedding model update by triggering background re-index.
        """
        repo_id = event.data.get("repo_id")
        if repo_id:
            logger.info(
                f"[Codebase] Received embedding_updated event. Triggering background re-index for repo {repo_id}"
            )
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
            logger.info(
                f"[Codebase] Received project.switched event. Restoring watchers and index state for {path}"
            )
            try:
                from app.domain.codebase.indexing.manager import indexing_manager
                from app.domain.codebase.indexing.service import IndexingService

                service = IndexingService()
                repo_name = os.path.basename(path)
                repo = await service.get_or_create_repo(
                    path, repo_name, project_id=project_id
                )
                await indexing_manager.start_watching(path, repo.id)

                # Trigger Smart Full-Indexing for "Staleness Check"
                asyncio.create_task(indexing_manager.run_indexing_background(repo.id))
            except Exception as e:
                logger.exception(
                    f"[Codebase] Failed to handle project switch for {path}: {e}"
                )


@event_register()
class IndexingEventSubscriber:
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

            logger.info(
                f"[IndexingHandler] Started watching and indexing: {event.path}"
            )
        except Exception as e:
            logger.exception(
                f"[IndexingHandler] Failed to start indexing for {event.path}: {e}"
            )

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
            logger.exception(
                f"[IndexingHandler] Failed to stop watching {event.path}: {e}"
            )

    @event_subscribe(ProjectEventType.PROJECT_MOVED)
    async def on_project_moved(self, event: BaseEvent) -> None:
        """
        Handle project move/rename by updating watcher paths.
        """
        if not isinstance(event, ProjectMovedEvent):
            return

        logger.info(
            f"[IndexingHandler] Received ProjectMovedEvent: {event.src_path} -> {event.dest_path}"
        )

        try:
            from app.domain.codebase.indexing.manager import indexing_manager

            # Stop old path
            await indexing_manager.stop_watching(event.src_path)
            # Start new path
            await indexing_manager.start_watching(event.dest_path, event.repo_id)

            logger.info(
                f"[IndexingHandler] Updated watcher: {event.src_path} -> {event.dest_path}"
            )
        except Exception as e:
            logger.exception(f"[IndexingHandler] Failed to handle move: {e}")


@event_register()
class GenerationAutoDispatchSubscriber:
    """
    Listens for indexing completed events and auto-dispatches generation.

    This is the bridge between the indexing domain and the generation domain.
    When indexing finishes successfully for a project, this subscriber:
    1. Dispatches wiki, appmap, and summary generation as background tasks
    2. Tracks their status via the GenerationScheduler
    """

    @event_subscribe(IndexingEventType.INDEXING_COMPLETED)
    async def on_indexing_completed(self, event: BaseEvent) -> None:
        """Handle INDEXING_COMPLETED: auto-dispatch wiki/appmap/summary generation."""
        project_id = event.data.get("project_id")
        if not project_id:
            logger.warning("[GenerationAutoDispatch] No project_id in event, skipping")
            return

        logger.info(
            f"[GenerationAutoDispatch] Indexing completed for project {project_id}, "
            f"dispatching generation..."
        )

        try:
            from app.domain.codebase.generation.runner import run_generation_item
            from app.domain.codebase.generation.scheduler import dispatch_generation

            items = [
                GENERATION_ITEM_WIKI,
                GENERATION_ITEM_APPMAP,
                GENERATION_ITEM_SUMMARY,
            ]

            # Mark them as pending in the scheduler
            await dispatch_generation(project_id, items)

            # Fire-and-forget: run each generation item in the background
            for item in items:
                asyncio.create_task(run_generation_item(project_id, item))

            logger.info(
                f"[GenerationAutoDispatch] Dispatched {items} for project {project_id}"
            )
        except Exception as e:
            logger.exception(
                f"[GenerationAutoDispatch] Failed to dispatch generation "
                f"for project {project_id}: {e}"
            )
