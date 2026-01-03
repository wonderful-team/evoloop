
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
        
        # Track Active Jobs: project_id -> status dict
        # Status: "queuing", "indexing", "error", "done"
        self._active_jobs: Dict[int, str] = {}
        # Optional: Track last update time or details

    def get_project_status(self, project_id: int) -> str:
        """Get the current indexing status for a project."""
        return self._active_jobs.get(project_id, "idle")

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

    async def trigger_full_index(self, project_id: int, rebuild: bool = False):
        """
        Trigger a full index for a given project.
        Resolves project -> repositories and indexes each.
        Args:
            rebuild: If True, forces re-indexing of all files.
        """
        logger.info(f"Triggering full index for Project ID: {project_id} (Rebuild={rebuild})")
        self._active_jobs[project_id] = "indexing"
        
        try:
            async with AsyncSessionLocal() as session:
                # 1. Fetch Repositories for Project
                stmt = select(Repository).where(Repository.project_id == project_id)
                result = await session.execute(stmt)
                repos = result.scalars().all()
                
                if not repos:
                    logger.warning(f"No repositories found for Project ID {project_id}")
                    self._active_jobs[project_id] = "done" # nothing to do
                    return
    
                for repo in repos:
                    if repo.local_path:
                        # IndexingService.index_repository is async.
                        await self._service.index_repository(repo.local_path, repo.id, force=rebuild)
                        
                        # --- Phase 7: Auto-Hierarchy ---
                        try:
                            from app.domain.codebase.indexing.directory_summarizer import directory_summarizer
                            await directory_summarizer.summarize_directory(repo.project_id, "", recursive=True)
                        except Exception as e:
                            logger.error(f"Directory Summarization Failed: {e}")
                            
                self._active_jobs[project_id] = "done"
                
        except Exception as e:
            logger.error(f"Full Index Failed for Project {project_id}: {e}")
            self._active_jobs[project_id] = "error"

    async def trigger_full_index_for_repo(self, repo_id: int):
        """
        Trigger full index for a specific repo by ID.
        Useful when we already have the repo object (e.g. within switch handler).
        """
        # Note: This method is per-repo. To map to project status, we need project_id.
        # Ideally, we should fetch project_id and update status too.
        async with AsyncSessionLocal() as session:
            repo = await session.get(Repository, repo_id)
            if not repo or not repo.local_path:
                logger.warning(f"Repository {repo_id} not found or has no path")
                return
            
            project_id = repo.project_id
            if project_id:
                 self._active_jobs[project_id] = "indexing"
            
            logger.info(f"Triggering full index for Repo ID: {repo_id} ({repo.name})")
            
            try:
                await self._service.index_repository(repo.local_path, repo.id)
                if project_id:
                     self._active_jobs[project_id] = "done"
            except Exception as e:
                 logger.error(f"Repo Index failed: {e}")
                 if project_id:
                     self._active_jobs[project_id] = "error_repo"
            
    def run_indexing_background(self, repo_id: int):
        """
        Helper to run indexing in a fire-and-forget background task.
        Safe to call from sync or async contexts where we don't await the result.
        """
        asyncio.create_task(self.trigger_full_index_for_repo(repo_id))


# Global Instance
indexing_manager = IndexingManager()
