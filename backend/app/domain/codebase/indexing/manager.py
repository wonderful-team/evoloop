import asyncio
import logging
import os

from sqlalchemy import select

from app.domain.codebase.indexing.service import IndexingService
from app.domain.watchers import RepoWatcher
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models import Repository
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


class IndexingManager:
    """
    Manages active watchers for projects and handles manual indexing triggers.
    Singleton-ish usage recommended.
    """

    def __init__(self):
        self._watchers: dict[str, RepoWatcher] = {}  # path -> watcher
        self._service = IndexingService()  # Shared service
        self._lock_pool = LoopBoundResource(asyncio.Lock)

        # Track Active Jobs: project_id -> status dict
        # Status: "queuing", "indexing", "error", "done"
        self._active_jobs: dict[int, str] = {}
        # Optional: Track last update time or details

    def get_project_status(self, project_id: int) -> str:
        """Get the current indexing status for a project."""
        return self._active_jobs.get(project_id, "idle")

    async def start_watching(self, path: str, repo_id: int):
        """
        Start watching a directory. Idempotent.
        """
        async with self._lock_pool.get():
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
        async with self._lock_pool.get():
            if path in self._watchers:
                watcher = self._watchers.pop(path)
                watcher.stop()
                logger.info(f"Stopped watching {path}")

    async def stop_all(self):
        """Stop all watchers."""
        async with self._lock_pool.get():
            for _path, watcher in self._watchers.items():
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
                    self._active_jobs[project_id] = "done"  # nothing to do
                    return

                for repo in repos:
                    if repo.local_path:
                        # IndexingService.index_repository is async.
                        await self._service.index_repository(repo.local_path, repo.id, force=rebuild)

                        # --- Phase 7: Auto-Hierarchy ---
                        try:
                            from app.domain.codebase.indexing.directory_summarizer import (
                                directory_summarizer,
                            )
                            await directory_summarizer.summarize_directory(repo.project_id, "", recursive=True)
                        except Exception as e:
                            logger.error(f"Directory Summarization Failed: {e}")

                        # --- Project Cognitive Summary ---
                        # Now that we have the deep directory summary, we generate the High-Level Project Overview.
                        # This ensures the "Description" and "Concepts" reflect the actual codebase structure.
                        try:
                            from app.domain.project.summarizer import project_summarizer
                            # project_summarizer internal logic checks if it's already done (project.json exists)
                            # to avoid re-running on every restart, unless we force it?
                            # For now, we rely on its internal idempotency.
                            # repo.local_path is absolute or relative? It's usually absolute in DB if set properly, or relative to root.
                            # We assume it resolves correctly.

                            # We need project name. Repo name is usually project name.
                            await project_summarizer.add_project(repo.name, repo.local_path)
                        except Exception as e:
                            logger.error(f"Project Summarization Trigger Failed: {e}")

                        # --- Standards & Patterns Analysis ---
                        # Sample code to extract implicit style guidelines for the Agent to follow.
                        try:
                            from app.domain.codebase.indexing.standards import (
                                project_standards_analyst,
                            )
                            await project_standards_analyst.analyze_standards(repo.project_id, repo.local_path)
                        except Exception as e:
                            logger.error(f"Standards Analysis Failed: {e}")

                        # --- Tier 4 Dynamic Indexing (Omniscience) ---
                        # Pre-condition: Is this a Software Project?
                        try:
                            from app.domain.codebase.indexing.classifier import (
                                ProjectType,
                                project_classifier,
                            )

                            p_type = project_classifier.classify(repo.local_path)

                            if p_type == ProjectType.SOFTWARE:
                                logger.info("Project classified as SOFTWARE. Running Semantic Extraction (API/DB)...")
                                await self._run_semantic_extraction(repo.local_path, repo.project_id)
                            else:
                                logger.info(f"Project classified as {p_type}. Skipping Semantic Extraction.")

                        except Exception as e:
                            logger.error(f"Semantic Extraction Failed: {e}")

                self._active_jobs[project_id] = "done"
                # Update all repos for this project to completed
                await self._update_indexing_status_by_project(project_id, "completed")

        except Exception as e:
            logger.error(f"Full Index Failed for Project {project_id}: {e}")
            self._active_jobs[project_id] = "error"
            await self._update_indexing_status_by_project(project_id, "failed")

    def dispatch_full_index(self, project_id: int, rebuild: bool = False):
        """
        Dispatch the indexing task to Celery worker.
        """
        try:
            from app.domain.codebase.indexing.tasks import run_full_indexing_task

            self._active_jobs[project_id] = "queued"
            # Update repository indexing_status to "in_progress"
            asyncio.create_task(self._update_indexing_status_by_project(project_id, "in_progress"))
            run_full_indexing_task.delay(project_id, rebuild)
            logger.info(f"Dispatched full index task for Project {project_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch indexing task: {e}")
            self._active_jobs[project_id] = "error_dispatch"
            asyncio.create_task(self._update_indexing_status_by_project(project_id, "failed"))

    async def _update_indexing_status(self, repo_id: int, status: str):
        """Update indexing_status and last_indexed_at for a repository."""
        async with AsyncSessionLocal() as session:
            from app.models import Repository
            repo = await session.get(Repository, repo_id)
            if repo:
                repo.indexing_status = status
                if status in ("completed", "failed"):
                    from app.utils.time import utcnow
                    repo.last_indexed_at = utcnow()
                await session.commit()
                logger.debug(f"[IndexingManager] Updated repo {repo_id} indexing_status to {status}")

    async def _update_indexing_status_by_project(self, project_id: int, status: str):
        """Update indexing_status for all repositories of a project."""
        async with AsyncSessionLocal() as session:
            from app.models import Repository
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repos = result.scalars().all()
            for repo in repos:
                repo.indexing_status = status
                if status in ("completed", "failed"):
                    from app.utils.time import utcnow
                    repo.last_indexed_at = utcnow()
            await session.commit()
            logger.debug(f"[IndexingManager] Updated project {project_id} repos indexing_status to {status}")

    async def _run_semantic_extraction(self, repo_path: str, project_id: int):
        """
        Run semantic extractors for Software Projects (API endpoints, DB schemas).
        """
        from app.constants import SEMANTIC_EXTENSIONS, SEMANTIC_LANGUAGE_MAP
        from app.core.file.service import walk_tree
        from app.domain.codebase.filter import FileFilter
        from app.domain.codebase.indexing.extractors.api_extractor import api_extractor
        from app.domain.codebase.indexing.extractors.db_extractor import db_extractor

        file_filter = FileFilter()

        # Walk once
        try:
            for full_path in walk_tree(repo_path, filter_func=file_filter.should_include):
                ext = os.path.splitext(full_path)[1].lower()

                # Check if file is a supported semantic language type
                if ext not in SEMANTIC_EXTENSIONS:
                    continue

                # API Extraction
                endpoints = await api_extractor.extract(full_path)
                if endpoints:
                    await api_extractor.sync_to_graph(project_id, endpoints)

                # DB Extraction (Currently limited to Python)
                if ext in SEMANTIC_LANGUAGE_MAP["python"]:
                    tables = await db_extractor.extract(full_path)
                    if tables:
                        await db_extractor.sync_to_graph(project_id, tables)

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

    async def run_indexing_background(self, repo_id: int):
        """
        Helper to run indexing in a fire-and-forget background task.
        
        NOTE: This is an async method but should NOT be awaited by caller.
        Use asyncio.create_task(run_indexing_background(...)) instead.
        """
        # Fire and forget - create task without awaiting
        asyncio.create_task(self._resolve_and_dispatch(repo_id))

    async def _resolve_and_dispatch(self, repo_id: int):
        """Async helper to resolve repo and dispatch indexing."""
        try:
            async with AsyncSessionLocal() as session:
                repo = await session.get(Repository, repo_id)
                if repo and repo.project_id:
                    self.dispatch_full_index(repo.project_id)
                else:
                    logger.warning(f"Could not resolve project for repo {repo_id}, skipping dispatch")
        except Exception as e:
            logger.error(f"Error in _resolve_and_dispatch for repo {repo_id}: {e}")


# Global Instance
indexing_manager = IndexingManager()
