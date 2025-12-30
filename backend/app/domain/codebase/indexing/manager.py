
import asyncio
import logging
from typing import Dict

from sqlalchemy import select

from app.domain.codebase.indexing.service import IndexingService
from app.domain.watchers import RepoWatcher
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.database.sql.models import Repository

logger = logging.getLogger(__name__)

class IndexingManager:
    """
    Manages active watchers for projects and handles manual indexing triggers.
    Singleton-ish usage recommended.
    """
    def __init__(self):
        self._watchers: Dict[str, RepoWatcher] = {} # path -> watcher
        self._service = IndexingService() # Shared service
        self._lock = asyncio.Lock()

    async def start_watching(self, path: str, repo_id: int):
        """
        Start watching a directory. Idempotent.
        """
        async with self._lock:
            if path in self._watchers:
                logger.debug(f"Already watching {path}")
                return

            try:
                watcher = RepoWatcher(path, repo_id)
                watcher.start()
                self._watchers[path] = watcher
                logger.info(f"Started watching {path} (Repo ID: {repo_id})")
            except Exception as e:
                logger.error(f"Failed to start watcher for {path}: {e}")

    async def stop_watching(self, path: str):
        """
        Stop watching a directory.
        """
        async with self._lock:
            if path in self._watchers:
                watcher = self._watchers.pop(path)
                watcher.stop()
                logger.info(f"Stopped watching {path}")

    async def stop_all(self):
        """Stop all watchers."""
        async with self._lock:
            for path, watcher in self._watchers.items():
                watcher.stop()
            self._watchers.clear()
            logger.info("Stopped all watchers")

    async def trigger_full_index(self, project_id: int):
        """
        Trigger a full index for a given project.
        Resolves project -> repositories and indexes each.
        """
        logger.info(f"Triggering full index for Project ID: {project_id}")
        
        async with AsyncSessionLocal() as session:
            # 1. Fetch Repositories for Project
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repos = result.scalars().all()
            
            if not repos:
                logger.warning(f"No repositories found for Project ID {project_id}")
                # If implicit project (just a folder), maybe we need to find it?
                # For now, we assume repos are created when 'scanned' or 'activated'.
                # Use project_context_manager logic if needed? 
                # Actually, IndexingService.get_or_create_repo handles creation. 
                # If it's a new project that was never indexed, it might not have a repo record yet!
                return

            for repo in repos:
                if repo.local_path:
                    # Run in background (this method itself is async, likely called from BackgroundTasks)
                    # IndexingService.index_repository is async.
                    await self._service.index_repository(repo.local_path, repo.id)

# Global Instance
indexing_manager = IndexingManager()
