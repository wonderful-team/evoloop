import logging
import asyncio

from app.core.events.base import BaseEvent, system_bus

logger = logging.getLogger(__name__)


async def handle_system_event(event: BaseEvent):
    """
    Handle cross-domain system events for the codebase domain.
    """
    if event.event_type == "system.embedding_updated":
        repo_id = event.data.get("repo_id")
        if repo_id:
            logger.info(f"[Codebase] Received embedding_updated event. Triggering background re-index for repo {repo_id}")
            from app.domain.codebase.indexing.manager import indexing_manager
            # Run in background without awaiting the entire indexing process to block the event bus
            asyncio.create_task(indexing_manager.run_indexing_background(repo_id))
    elif event.event_type == "project.switched":
        project_id = event.data.get("project_id")
        path = event.data.get("path")
        if path and project_id:
            logger.info(f"[Codebase] Received project.switched event. Restoring watchers and index state for {path}")
            try:
                from app.domain.codebase.indexing.manager import indexing_manager
                from app.domain.codebase.indexing.service import IndexingService
                import os
                
                service = IndexingService()
                repo_name = os.path.basename(path)
                repo = await service.get_or_create_repo(path, repo_name, project_id=project_id)
                await indexing_manager.start_watching(path, repo.id)
                
                # Trigger Smart Full-Indexing for "Staleness Check"
                asyncio.create_task(indexing_manager.run_indexing_background(repo.id))
            except Exception as e:
                logger.error(f"[Codebase] Failed to handle project switch for {path}: {e}")


def register_codebase_events():
    """Register codebase domain listeners to the system event bus."""
    system_bus.subscribe("system.embedding_updated", handle_system_event)
    system_bus.subscribe("project.switched", handle_system_event)
    logger.info("📡 Codebase domain event listeners registered")
