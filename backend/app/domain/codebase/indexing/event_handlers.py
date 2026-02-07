"""
Indexing Domain Event Handlers

Subscribes to project events to trigger indexing operations.
This decouples IndexingManager from ProjectSyncService.
"""

import logging

from app.core.events.base import BaseEvent
from app.core.events.registry import ProjectEventType
from app.domain.project.events import ProjectCreatedEvent, ProjectDeletedEvent, ProjectMovedEvent

logger = logging.getLogger(__name__)


class IndexingEventHandler:
    """
    Handles project events to trigger indexing operations.
    
    This handler bridges the project domain with the indexing domain,
    enabling loose coupling between these components.
    """
    
    @staticmethod
    async def on_project_created(event: BaseEvent) -> None:
        """
        Handle project creation by starting file watching and indexing.
        """
        if not isinstance(event, ProjectCreatedEvent):
            return
        
        logger.info(f"[IndexingHandler] Received ProjectCreatedEvent for: {event.path}")
        
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            
            await indexing_manager.start_watching(event.path, event.repo_id)
            await indexing_manager.run_indexing_background(event.repo_id)
            
            logger.info(f"[IndexingHandler] Started watching and indexing: {event.path}")
        except Exception as e:
            logger.error(f"[IndexingHandler] Failed to start indexing for {event.path}: {e}")
    
    @staticmethod
    async def on_project_deleted(event: BaseEvent) -> None:
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
    
    @staticmethod
    async def on_project_moved(event: BaseEvent) -> None:
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


def register_indexing_handlers() -> None:
    """
    Register indexing event handlers with the system bus.
    
    Should be called during application startup (in main.py lifespan).
    """
    from app.core.events import system_bus
    
    system_bus.subscribe(ProjectEventType.PROJECT_CREATED, IndexingEventHandler.on_project_created)
    system_bus.subscribe(ProjectEventType.PROJECT_DELETED, IndexingEventHandler.on_project_deleted)
    system_bus.subscribe(ProjectEventType.PROJECT_MOVED, IndexingEventHandler.on_project_moved)
    
    logger.info("📡 Indexing event handlers registered")
