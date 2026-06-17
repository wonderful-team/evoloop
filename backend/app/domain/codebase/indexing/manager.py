import asyncio
import logging
import os
import threading

from sqlalchemy import select

from app.core.project.utils import get_project_path
from app.domain.codebase.indexing.service import IndexingService
from app.domain.watchers import RepoWatcher
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database.sql.database import session_scope
from app.models import Repository

logger = logging.getLogger(__name__)


class IndexingManager:
    """
    Manages active watchers for projects and handles manual indexing triggers.
    Singleton-ish usage recommended.

    Cancellation:
        Call ``cancel_indexing(project_id)`` to set a cancellation flag.
        ``trigger_full_index`` checks this flag between phases and before
        each repository is indexed, so cancellation is prompt but not
        immediate (no thread interruption).
    """

    def __init__(self):
        self._watchers: dict[str, RepoWatcher] = {}  # path -> watcher
        # Use a threading.Lock because IndexingManager is a process-level
        # singleton that may be accessed by multiple Huey worker threads.
        self._lock = threading.Lock()

        # Track Active Jobs: project_id -> status dict
        # Status: "queuing", "indexing", "error", "done", "cancelled"
        self._active_jobs: dict[int, str] = {}
        # Cancellation flags — checked during trigger_full_index
        self._cancel_flags: dict[int, threading.Event] = {}

    def get_project_status(self, project_id: int) -> str:
        """Get the current indexing status for a project."""
        with self._lock:
            return self._active_jobs.get(project_id, "idle")

    def cancel_indexing(self, project_id: int) -> None:
        """Request cancellation of an active full-index job for a project."""
        with self._lock:
            flag = self._cancel_flags.get(project_id)
            if flag is not None:
                flag.set()
                logger.info(
                    f"[IndexingManager] Cancel requested for project {project_id}"
                )
            else:
                logger.warning(
                    f"[IndexingManager] No active job to cancel for project {project_id}"
                )

    def _check_cancelled(self, project_id: int) -> bool:
        """Return True if cancellation has been requested for this project."""
        with self._lock:
            flag = self._cancel_flags.get(project_id)
            if flag and flag.is_set():
                logger.info(f"[IndexingManager] Job cancelled for project {project_id}")
                self._active_jobs[project_id] = "cancelled"
                self._cancel_flags.pop(project_id, None)
                return True
            return False

    async def start_watching(self, path: str, repo_id: int):
        """
        Start watching a directory. Idempotent.
        """
        with self._lock:
            # Check if WORKSPACE_ROOT is configured
            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            if not workspace_root:
                logger.warning(
                    f"[IndexingManager] WORKSPACE_ROOT not configured. Skipping watch for: {path}"
                )
                return

            # Ensure path is within WORKSPACE_ROOT
            abs_path = os.path.abspath(path)
            abs_root = os.path.abspath(workspace_root)
            if not abs_path.startswith(abs_root):
                logger.warning(
                    f"[IndexingManager] Path {path} is outside WORKSPACE_ROOT ({workspace_root}). Skipping watch."
                )
                return

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
        with self._lock:
            if path in self._watchers:
                watcher = self._watchers.pop(path)
                watcher.stop()
                logger.info(f"Stopped watching {path}")

    async def stop_all(self):
        """Stop all watchers."""
        with self._lock:
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
        logger.info(
            f"Triggering full index for Project ID: {project_id} (Rebuild={rebuild})"
        )
        # Use a local service instance so concurrent calls do not share mutable
        # component state across threads.
        service = IndexingService()
        with self._lock:
            self._active_jobs[project_id] = "indexing"
            self._cancel_flags[project_id] = threading.Event()

        try:
            async with session_scope() as session:
                # 1. Fetch Repositories for Project
                stmt = select(Repository).where(Repository.project_id == project_id)
                result = await session.execute(stmt)
                repos = result.scalars().all()

                if not repos:
                    logger.warning(f"No repositories found for Project ID {project_id}")
                    with self._lock:
                        self._active_jobs[project_id] = "done"
                    return

                for repo in repos:
                    if self._check_cancelled(project_id):
                        return

                    repo_path = await self._resolve_repo_path(repo)
                    if not repo_path:
                        logger.warning(
                            f"[IndexingManager] Could not resolve local path for repo {repo.id} (project {repo.project_id}). Skipping."
                        )
                        continue

                    await service.index_repository(repo_path, repo.id, force=rebuild)

                    if self._check_cancelled(project_id):
                        return

                    # --- Phase 7: Auto-Hierarchy ---
                    try:
                        from app.domain.codebase.indexing.directory_summarizer import (
                            directory_summarizer,
                        )

                        await directory_summarizer.summarize_directory(
                            repo_path, repo.project_id, "", recursive=True
                        )
                    except Exception as e:
                        logger.error(f"Directory Summarization Failed: {e}")

                    if self._check_cancelled(project_id):
                        return

                    # --- Project Cognitive Summary ---
                    try:
                        from app.core.project.summarizer import project_summarizer

                        await project_summarizer.add_project(repo.name, repo_path)
                    except Exception as e:
                        logger.error(f"Project Summarization Trigger Failed: {e}")

                    if self._check_cancelled(project_id):
                        return

                    # --- Standards & Patterns Analysis ---
                    try:
                        from app.domain.codebase.indexing.standards import (
                            project_standards_analyst,
                        )

                        await project_standards_analyst.analyze_standards(
                            repo.project_id, repo_path
                        )
                    except Exception as e:
                        logger.error(f"Standards Analysis Failed: {e}")

                    if self._check_cancelled(project_id):
                        return

                    # --- Tier 4 Dynamic Indexing (Omniscience) ---
                    try:
                        from app.domain.codebase.indexing.classifier import (
                            ProjectType,
                            project_classifier,
                        )

                        p_type = project_classifier.classify(repo_path)

                        if p_type == ProjectType.SOFTWARE:
                            logger.info(
                                "Project classified as SOFTWARE. Running Semantic Extraction (API/DB)..."
                            )
                            await self._run_semantic_extraction(
                                repo_path, repo.project_id
                            )
                        else:
                            logger.info(
                                f"Project classified as {p_type}. Skipping Semantic Extraction."
                            )

                    except Exception as e:
                        logger.error(f"Semantic Extraction Failed: {e}")

                with self._lock:
                    self._active_jobs[project_id] = "done"
                # Update all repos for this project to completed
                await self._update_indexing_status_by_project(project_id, "completed")

        except Exception as e:
            logger.error(f"Full Index Failed for Project {project_id}: {e}")
            with self._lock:
                self._active_jobs[project_id] = "error"
            await self._update_indexing_status_by_project(project_id, "failed")

    def dispatch_full_index(self, project_id: int, rebuild: bool = False):
        """
        Dispatch the indexing task to Celery worker.
        Clears any previous cancellation flag for this project.
        """
        try:
            from app.domain.codebase.indexing.tasks import run_full_indexing_task

            with self._lock:
                self._active_jobs[project_id] = "queued"
                self._cancel_flags.pop(project_id, None)  # Reset cancel flag
            # Update repository indexing_status to "in_progress"
            run_full_indexing_task.delay(project_id, rebuild)
            logger.info(f"Dispatched full index task for Project {project_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch indexing task: {e}")
            with self._lock:
                self._active_jobs[project_id] = "error_dispatch"

    async def _update_indexing_status(self, repo_id: int, status: str):
        """Update indexing_status and last_indexed_at for a repository."""
        async with session_scope() as session:
            from app.models import Repository

            repo = await session.get(Repository, repo_id)
            if repo:
                repo.indexing_status = status
                if status in ("completed", "failed"):
                    from app.utils.time import utcnow

                    repo.last_indexed_at = utcnow()
                logger.debug(
                    f"[IndexingManager] Updated repo {repo_id} indexing_status to {status}"
                )

    async def _update_indexing_status_by_project(self, project_id: int, status: str):
        """Update indexing_status for all repositories of a project."""
        async with session_scope() as session:
            from app.models import Repository

            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repos = result.scalars().all()
            for repo in repos:
                repo.indexing_status = status
                if status in ("completed", "failed"):
                    from app.utils.time import utcnow

                    repo.last_indexed_at = utcnow()
            logger.debug(
                f"[IndexingManager] Updated project {project_id} repos indexing_status to {status}"
            )

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

        # Walk once. Offload the synchronous filesystem walk to a thread so it
        # does not block the asyncio event loop for large repositories.
        try:
            file_paths = await asyncio.to_thread(
                lambda: list(
                    walk_tree(repo_path, filter_func=file_filter.should_include)
                )
            )
            for full_path in file_paths:
                ext = os.path.splitext(full_path)[1].lower()

                # Check if file is a supported semantic language type
                if ext not in SEMANTIC_EXTENSIONS:
                    continue

                # API Extraction
                entities = await api_extractor.extract(full_path)
                if entities:
                    await api_extractor.sync_to_graph(repo_path, project_id, entities)

                # DB Extraction (Currently limited to Python)
                if ext in SEMANTIC_LANGUAGE_MAP["python"]:
                    tables = await db_extractor.extract(full_path)
                    if tables:
                        await db_extractor.sync_to_graph(repo_path, project_id, tables)

        except Exception as e:
            logger.error(f"Full Index Failed for Project {project_id}: {e}")
            with self._lock:
                self._active_jobs[project_id] = "error"

    async def _resolve_repo_path(self, repo: Repository) -> str | None:
        """Resolve the local filesystem path for a repository.

        Prefer the authoritative project_id -> path resolution, falling back to
        the repository's own stored paths only when necessary.
        """
        if repo.project_id is not None:
            resolved = await get_project_path(repo.project_id)
            if resolved and os.path.isdir(resolved):
                return resolved
        if repo.local_path and os.path.isdir(repo.local_path):
            return repo.local_path
        return None

    async def trigger_full_index_for_repo(self, repo_id: int):
        """
        Trigger full index for a specific repo by ID.
        Useful when we already have the repo object (e.g. within switch handler).
        """
        # Note: This method is per-repo. To map to project status, we need project_id.
        # Ideally, we should fetch project_id and update status too.
        async with session_scope() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                logger.warning(f"Repository {repo_id} not found")
                return

            repo_path = await self._resolve_repo_path(repo)
            if not repo_path:
                logger.warning(f"Repository {repo_id} has no resolvable local path")
                return

            project_id = repo.project_id
            if project_id is not None:
                with self._lock:
                    self._active_jobs[project_id] = "indexing"

            logger.info(f"Triggering full index for Repo ID: {repo_id} ({repo.name})")

            # Use a local service instance for thread safety.
            service = IndexingService()
            try:
                await service.index_repository(repo_path, repo.id)
                if project_id is not None:
                    with self._lock:
                        self._active_jobs[project_id] = "done"
            except Exception as e:
                logger.error(f"Repo Index failed: {e}")
                if project_id is not None:
                    with self._lock:
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
            async with session_scope() as session:
                repo = await session.get(Repository, repo_id)
                if repo and repo.project_id:
                    self.dispatch_full_index(repo.project_id)
                else:
                    logger.warning(
                        f"Could not resolve project for repo {repo_id}, skipping dispatch"
                    )
        except Exception as e:
            logger.error(f"Error in _resolve_and_dispatch for repo {repo_id}: {e}")


# Global Instance
indexing_manager = IndexingManager()
