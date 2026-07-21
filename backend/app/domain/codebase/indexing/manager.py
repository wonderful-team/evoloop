import asyncio
import logging
import os
import threading
from typing import Any

from sqlalchemy import delete, select

from app.core.file import read_file
from app.core.project.utils import get_project_path, resolve_project_to_repo
from app.domain.codebase.indexing.service import IndexingService
from app.domain.codebase.security import scan_file
from app.domain.watchers import RepoWatcher
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database import session_scope
from app.models import CodeChunk, Repository, SecurityFinding, SourceFile

logger = logging.getLogger(__name__)


def _indexing_status_key(repo_id: int) -> str:
    """Cache hash key used to expose real-time repo indexing status."""
    return f"sys:{repo_id}:indexing"


def _cancel_key(repo_id: int) -> str:
    """Cache key used to request cancellation of a repo indexing job."""
    return f"indexing:cancel:{repo_id}"


async def _set_indexing_status(repo_id: int, status: str, details: dict | None = None) -> None:
    """Persist repo indexing status to cache for real-time API reads."""
    try:
        mapping = {"status": status}
        if details:
            import json

            for key, value in details.items():
                mapping[key] = json.dumps(value) if isinstance(value, dict | list) else str(value)
        await cache.hset(_indexing_status_key(repo_id), mapping=mapping)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[IndexingManager] Failed to write status cache for repo {repo_id}: {e}")


async def _clear_cancel_flag(repo_id: int) -> None:
    """Clear any pending cancellation request for a repo."""
    try:
        await cache.delete(_cancel_key(repo_id))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[IndexingManager] Failed to clear cancel flag for repo {repo_id}: {e}")


async def _request_cancel(repo_id: int) -> None:
    """Request cancellation of a repo indexing job via persistent cache flag."""
    try:
        await cache.set(_cancel_key(repo_id), "1")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[IndexingManager] Failed to set cancel flag for repo {repo_id}: {e}")


async def _is_cancel_requested(repo_id: int) -> bool:
    """Return True if cancellation has been requested for this repo."""
    try:
        return bool(await cache.get(_cancel_key(repo_id)))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"[IndexingManager] Failed to read cancel flag for repo {repo_id}: {e}")
        return False


class IndexingManager:
    """
    Manages active watchers for repositories and handles manual indexing triggers.
    Singleton-ish usage recommended.

    Internal scheduling, status tracking and cancellation are keyed by repo_id.
    project_id is only used for project-level side effects (summarization,
    standards, graph sync) and for frontend-facing events/status aggregation.

    Cancellation:
        Call ``cancel_repo_index(repo_id)`` (or ``cancel_indexing(project_id)``)
        to set a persistent cancellation flag. ``trigger_full_index_repo`` checks
        this flag between phases so cancellation is prompt but not immediate.
    """

    def __init__(self):
        self._watchers: dict[str, RepoWatcher] = {}  # path -> watcher
        # Use a threading.Lock because IndexingManager is a process-level
        # singleton that may be accessed by multiple Huey worker threads.
        self._lock = threading.Lock()

        # Track Active Jobs: repo_id -> status dict
        # Status: "queuing", "indexing", "error", "done", "cancelled"
        self._active_jobs: dict[int, str] = {}

    def get_repo_status(self, repo_id: int) -> str:
        """Get the current in-memory indexing status for a repository."""
        with self._lock:
            return self._active_jobs.get(repo_id, "idle")

    async def cancel_repo_index(self, repo_id: int) -> None:
        """Request cancellation of an active full-index job for a repository."""
        await _request_cancel(repo_id)
        with self._lock:
            self._active_jobs[repo_id] = "cancelled"
        logger.info(f"[IndexingManager] Cancel requested for repo {repo_id}")

    def cancel_indexing(self, project_id: int) -> None:
        """
        Request cancellation of active full-index job(s) for a project.

        This synchronous wrapper schedules async cancellation for all repos
        associated with the project. It exists for backward compatibility.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._cancel_by_project(project_id))
        except RuntimeError:
            logger.warning(
                f"[IndexingManager] No running event loop; cannot schedule cancellation for project {project_id}"
            )

    async def _cancel_by_project(self, project_id: int) -> None:
        """Resolve active repo(s) for a project and request cancellation."""
        repo = await resolve_project_to_repo(project_id)
        if repo:
            await self.cancel_repo_index(repo.id)
        else:
            logger.warning(
                f"[IndexingManager] No active repo to cancel for project {project_id}"
            )

    async def _check_cancelled(self, repo_id: int) -> bool:
        """Return True if cancellation has been requested for this repo."""
        if await _is_cancel_requested(repo_id):
            logger.info(f"[IndexingManager] Job cancelled for repo {repo_id}")
            with self._lock:
                self._active_jobs[repo_id] = "cancelled"
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
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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

    async def trigger_full_index_repo(self, repo_id: int, rebuild: bool = False):
        """
        Trigger a full index for a specific repository.

        Args:
            repo_id: The local repository ID to index.
            rebuild: If True, forces re-indexing of all files.
        """
        logger.info(f"Triggering full index for Repo ID: {repo_id} (Rebuild={rebuild})")

        service = IndexingService()
        with self._lock:
            self._active_jobs[repo_id] = "indexing"
        await _clear_cancel_flag(repo_id)

        try:
            async with session_scope() as session:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.warning(f"Repository {repo_id} not found")
                    with self._lock:
                        self._active_jobs[repo_id] = "error"
                    await _set_indexing_status(repo_id, "error")
                    return

                project_id = repo.project_id
                repo_path = await self._resolve_repo_path(repo)
                if not repo_path:
                    logger.warning(
                        f"[IndexingManager] Could not resolve local path for repo {repo_id}"
                    )
                    with self._lock:
                        self._active_jobs[repo_id] = "error"
                    await _set_indexing_status(repo_id, "error")
                    await self._update_indexing_status(repo_id, "failed")
                    return

                await self._update_indexing_status(repo_id, "in_progress")
                await _set_indexing_status(repo_id, "indexing")
                await self._publish_status(project_id, repo_id, "indexing")

                if await self._check_cancelled(repo_id):
                    return

                await service.index_repository(repo_path, repo_id, force=rebuild)

                if await self._check_cancelled(repo_id):
                    return

                # --- Phase 7: Auto-Hierarchy ---
                try:
                    from app.domain.codebase.indexing.directory_summarizer import (
                        directory_summarizer,
                    )

                    await directory_summarizer.summarize_directory(
                        repo_path, project_id, "", recursive=True
                    )
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Directory Summarization Failed: {e}")

                if await self._check_cancelled(repo_id):
                    return

                # --- Project Cognitive Summary ---
                try:
                    from app.core.project.summarizer import project_summarizer

                    await project_summarizer.add_project(repo.name, repo_path)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Project Summarization Trigger Failed: {e}")

                if await self._check_cancelled(repo_id):
                    return

                # --- Standards & Patterns Analysis ---
                try:
                    from app.domain.codebase.indexing.standards import (
                        project_standards_analyst,
                    )

                    await project_standards_analyst.analyze_standards(
                        project_id, repo_path
                    )
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Standards Analysis Failed: {e}")

                if await self._check_cancelled(repo_id):
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
                        await self._run_semantic_extraction(repo_id, repo_path, project_id)
                    else:
                        logger.info(
                            f"Project classified as {p_type}. Skipping Semantic Extraction."
                        )

                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Semantic Extraction Failed: {e}")

                with self._lock:
                    self._active_jobs[repo_id] = "done"
                await _set_indexing_status(repo_id, "done")
                await self._publish_status(project_id, repo_id, "done")
                await self._update_indexing_status(repo_id, "completed")

                if project_id is not None:
                    from app.domain.codebase.event.publishers import publish_indexing_completed
                    asyncio.create_task(publish_indexing_completed(project_id, repo_id))

        except asyncio.CancelledError:
            logger.info(f"Full Index Cancelled for Repo {repo_id}")
            with self._lock:
                self._active_jobs[repo_id] = "cancelled"
            await _set_indexing_status(repo_id, "cancelled")
            await self._publish_status(project_id, repo_id, "cancelled")
            await self._update_indexing_status(repo_id, "failed")
            raise
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Full Index Failed for Repo {repo_id}: {e}")
            with self._lock:
                self._active_jobs[repo_id] = "error"
            await _set_indexing_status(repo_id, "error")
            await self._publish_status(project_id, repo_id, "error")
            await self._update_indexing_status(repo_id, "failed")

    def dispatch_full_index(self, project_id: int, rebuild: bool = False):
        """
        Dispatch the indexing task for a project.

        Resolves the project to its active local repo and queues a repo-level
        indexing task. Keeps the external API surface on project_id.
        """
        try:
            # Synchronous resolution path: schedule an async helper to look up the
            # repo and dispatch. This keeps the API endpoint non-blocking while
            # still ensuring we only dispatch for resolvable repos.
            coro = self._resolve_and_dispatch_repo_task(project_id, rebuild)
            try:
                asyncio.create_task(coro)
            except RuntimeError:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(lambda: asyncio.create_task(coro))

            logger.info(f"Dispatched full index task for Project {project_id}")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Failed to dispatch indexing task: {e}")

    async def _resolve_and_dispatch_repo_task(self, project_id: int, rebuild: bool) -> None:
        """Async helper to resolve project -> repo and dispatch the indexing task."""
        try:
            repo = await resolve_project_to_repo(project_id)
            if not repo:
                logger.warning(
                    f"[IndexingManager] Could not resolve active repo for project {project_id}, skipping dispatch"
                )
                return

            await self._dispatch_repo_index(repo.id, rebuild)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[IndexingManager] Error dispatching index for project {project_id}: {e}")

    async def _dispatch_repo_index(self, repo_id: int, rebuild: bool = False) -> None:
        """Dispatch a repo-level full-index task to the queue."""
        from app.domain.codebase.indexing.tasks import run_full_indexing_task

        project_id = None
        try:
            async with session_scope() as session:
                repo = await session.get(Repository, repo_id)
                project_id = repo.project_id if repo else None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[IndexingManager] Could not resolve project_id for repo {repo_id}: {e}")

        with self._lock:
            self._active_jobs[repo_id] = "queued"
        await _clear_cancel_flag(repo_id)
        await _set_indexing_status(repo_id, "queued")
        await self._publish_status(project_id, repo_id, "queued")
        run_full_indexing_task.delay(repo_id, rebuild)
        logger.info(f"Dispatched full index task for Repo {repo_id}")

    async def _update_indexing_status(self, repo_id: int, status: str):
        """Update indexing_status and last_indexed_at for a repository."""
        async with session_scope() as session:
            repo = await session.get(Repository, repo_id)
            if repo:
                repo.indexing_status = status
                if status in ("completed", "failed"):
                    from app.utils.time import utcnow

                    repo.last_indexed_at = utcnow()
                logger.debug(
                    f"[IndexingManager] Updated repo {repo_id} indexing_status to {status}"
                )

    async def _publish_status(self, project_id: int | None, repo_id: int, status: str) -> None:
        """Notify frontend of status change via SSE."""
        if project_id is None:
            return
        try:
            from app.domain.codebase.event.publishers import (
                publish_indexing_status_changed,
            )

            await publish_indexing_status_changed(project_id, status, repo_id=repo_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[IndexingManager] Failed to publish indexing status event: {e}")

    async def _run_semantic_extraction(self, repo_id: int, repo_path: str, project_id: int | None):
        """
        Security scan + mark code chunks as API routes / DB models using
        Tree-sitter parsed data — no language-specific regex.
        """
        from app.constants import SEMANTIC_EXTENSIONS
        from app.core.file.service import walk_tree
        from app.domain.codebase.filter import FileFilter
        from app.models.codebase import SourceFile, CodeChunk
        from sqlalchemy import select

        controller_patterns = {
            "controller", "controllers", "handler", "handlers",
            "action", "actions", "resource", "endpoint", "api",
        }
        model_patterns = {
            "model", "models", "entity", "entities", "bean", "beans",
            "domain", "dto", "vo", "bo", "table", "tables", "po", "persistence",
        }

        file_filter = FileFilter()
        has_routes = False
        has_models = False

        try:
            # Walk files for security scanning (still needed)
            file_paths = await asyncio.to_thread(
                lambda: list(
                    walk_tree(
                        repo_path,
                        filter_func=file_filter.should_include,
                        gitignore_root=repo_path,
                    )
                )
            )

            # Collect source file IDs by type via path conventions
            file_ids_by_type: dict[str, list[int]] = {"controller": [], "model": []}
            source_files_map: dict[str, SourceFile] = {}

            for full_path in file_paths:
                ext = os.path.splitext(full_path)[1].lower()
                if ext not in SEMANTIC_EXTENSIONS:
                    continue

                rel_path = os.path.relpath(full_path, repo_path)

                # Security scan (reads file content — unavoidable)
                content = await self._read_file_for_scan(full_path)
                if content is not None:
                    await self._persist_security_findings(repo_id, rel_path, content)

            # Now classify via DB — no regex, no file re-reading
            async with session_scope() as session:
                result = await session.execute(
                    select(SourceFile).where(
                        SourceFile.repository_id == repo_id,
                        SourceFile.scan_status == "completed",
                    )
                )
                for sf in result.scalars().all():
                    ext = os.path.splitext(sf.path)[1].lower()
                    if ext not in SEMANTIC_EXTENSIONS:
                        continue
                    parts = sf.path.lower().split("/")
                    stem = os.path.splitext(parts[-1])[0]
                    if any(p in controller_patterns for p in parts) \
                       or any(stem.endswith(s) for s in ("controller", "handler", "action", "resource")):
                        file_ids_by_type["controller"].append(sf.id)
                    if any(p in model_patterns for p in parts) \
                       or any(stem.endswith(s) for s in ("model", "entity", "bean")):
                        file_ids_by_type["model"].append(sf.id)

                if file_ids_by_type["controller"]:
                    cr = await session.execute(
                        select(CodeChunk).where(
                            CodeChunk.source_file_id.in_(file_ids_by_type["controller"]),
                            CodeChunk.chunk_type.in_(["function", "method"]),
                        )
                    )
                    for chunk in cr.scalars().all():
                        name = chunk.identifier.split(".")[-1].split("::")[-1]
                        if not name.startswith("_") and name not in ("__construct", "__destruct", "__init"):
                            chunk.is_api_route = True
                            has_routes = True

                if file_ids_by_type["model"]:
                    mr = await session.execute(
                        select(CodeChunk).where(
                            CodeChunk.source_file_id.in_(file_ids_by_type["model"]),
                            CodeChunk.chunk_type == "class",
                        )
                    )
                    for chunk in mr.scalars().all():
                        chunk.is_db_model = True
                        chunk.db_table_name = chunk.identifier.split(".")[-1].split("::")[-1]
                        has_models = True

                if has_routes or has_models:
                    await session.commit()

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Semantic Extraction Failed: {e}")
            return

        if not has_routes and not has_models:
            logger.info("Convention inference returned nothing, dispatching Agent...")
            await self._analyze_with_agent(repo_id, repo_path, project_id)

    async def _read_file_for_scan(self, file_path: str) -> str | None:
        """Read file content for the security scanner."""
        try:
            result = read_file(file_path)
            return result.content if result.success else None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"Failed to read file for security scan {file_path}: {e}")
            return None

    async def _persist_security_findings(
        self, repo_id: int, rel_path: str, content: str
    ) -> None:
        """Run security scan and persist findings. Failures are non-blocking."""
        try:
            findings = scan_file(rel_path, content)
            async with session_scope() as session:
                stmt = select(SourceFile).where(
                    SourceFile.repository_id == repo_id,
                    SourceFile.path == rel_path,
                )
                result = await session.execute(stmt)
                source_file = result.scalars().first()
                if source_file is None:
                    return

                await session.execute(
                    delete(SecurityFinding).where(
                        SecurityFinding.source_file_id == source_file.id
                    )
                )

                if findings:
                    for finding in findings:
                        session.add(
                            SecurityFinding(
                                source_file_id=source_file.id,
                                finding_type=finding.finding_type,
                                severity=finding.severity,
                                description=finding.description,
                                line_start=finding.line_start,
                                line_end=finding.line_end,
                                code_snippet=finding.code_snippet,
                            )
                        )
                source_file.security_scan_status = "completed"
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Security scan failed for {rel_path}: {e}")
            try:
                async with session_scope() as session:
                    stmt = select(SourceFile).where(
                        SourceFile.repository_id == repo_id,
                        SourceFile.path == rel_path,
                    )
                    result = await session.execute(stmt)
                    source_file = result.scalars().first()
                    if source_file is not None:
                        source_file.security_scan_status = "failed"
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as mark_err:
                logger.error(f"Failed to mark security_scan_status as failed: {mark_err}")

    async def _analyze_with_agent(self, repo_id: int, repo_path: str, project_id: int | None) -> None:
        """Dispatch an Agent to analyze project structure when convention inference fails.

        The Agent uses existing file tools to:
        1. Read project config files (composer.json, package.json, etc.)
        2. Identify framework and routes
        3. Extract DB models
        4. Return structured data

        Results are persisted as API endpoints and DB tables.
        """
        logger.info(f"Agent analysis dispatched for repo {repo_id} at {repo_path}")
        try:
            from app.core.engine.inference_engine import InferenceEngine
            from app.domain.codebase.schemas import APIEndpoint, DBTable

            engine = InferenceEngine()
            agent_result = await engine.analyze_codebase(
                repo_path=repo_path,
                task="infer_api_and_db",
                project_id=project_id,
            )

            if not agent_result:
                logger.info(f"Agent returned no results for repo {repo_id}")
                return

            endpoints = agent_result.get("endpoints", [])
            tables = agent_result.get("tables", [])

            for ep_data in endpoints:
                ep = APIEndpoint(**ep_data)
                rel_path = ep.file_path
                await self._update_api_chunk_flags(repo_id, rel_path, [ep])

            for table_data in tables:
                table = DBTable(**table_data)
                rel_path = table.file_path
                await self._update_db_chunk_flags(repo_id, rel_path, [table])

            logger.info(
                f"Agent analysis for repo {repo_id}: "
                f"{len(endpoints)} endpoints, {len(tables)} tables"
            )

        except Exception as e:
            logger.error(f"Agent analysis failed for repo {repo_id}: {e}")

    async def _update_api_chunk_flags(
        self, repo_id: int, rel_path: str, entities: list
    ) -> None:
        """Update CodeChunk rows from extracted API endpoints."""
        try:
            async with session_scope() as session:
                stmt = select(SourceFile).where(
                    SourceFile.repository_id == repo_id,
                    SourceFile.path == rel_path,
                )
                result = await session.execute(stmt)
                source_file = result.scalars().first()
                if source_file is None:
                    return

                for ep in entities:
                    handler_name = getattr(ep, "handler_name", "")
                    if not handler_name:
                        continue

                    await self._apply_chunk_flag(
                        session,
                        source_file.id,
                        handler_name,
                        is_api_route=True,
                        api_method=getattr(ep, "method", None),
                        api_path=getattr(ep, "path", None),
                    )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Failed to update API chunk flags: {e}")

    async def _update_db_chunk_flags(
        self, repo_id: int, rel_path: str, tables: list
    ) -> None:
        """Update CodeChunk rows from extracted DB tables."""
        try:
            async with session_scope() as session:
                stmt = select(SourceFile).where(
                    SourceFile.repository_id == repo_id,
                    SourceFile.path == rel_path,
                )
                result = await session.execute(stmt)
                source_file = result.scalars().first()
                if source_file is None:
                    return

                for table in tables:
                    table_name = getattr(table, "name", "")
                    if not table_name:
                        continue

                    await self._apply_chunk_flag(
                        session,
                        source_file.id,
                        table_name,
                        is_db_model=True,
                        db_table_name=table_name,
                    )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Failed to update DB chunk flags: {e}")

    async def _apply_chunk_flag(
        self,
        session,
        source_file_id: int,
        name: str,
        *,
        is_api_route: bool = False,
        api_method: str | None = None,
        api_path: str | None = None,
        is_db_model: bool = False,
        db_table_name: str | None = None,
    ) -> None:
        """Match a CodeChunk by source_file_id and identifier/name and update flags."""
        # CodeChunk identifiers are FQNs like "path/to/file.py::Class.method".
        # Match either the exact name or a suffix of the FQN.
        suffix_dot = f".{name}"
        suffix_colon = f"::{name}"

        stmt = select(CodeChunk).where(
            CodeChunk.source_file_id == source_file_id,
            (
                (CodeChunk.identifier == name)
                | CodeChunk.identifier.endswith(suffix_dot)
                | CodeChunk.identifier.endswith(suffix_colon)
            ),
        )
        result = await session.execute(stmt)
        chunk = result.scalars().first()
        if chunk is None:
            return

        if is_api_route:
            chunk.is_api_route = True
            if api_method:
                chunk.api_method = api_method.upper()
            if api_path:
                chunk.api_path = api_path
        if is_db_model:
            chunk.is_db_model = True
            if db_table_name:
                chunk.db_table_name = db_table_name

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

        Deprecated: use trigger_full_index_repo instead.
        """
        await self.trigger_full_index_repo(repo_id)

    async def run_indexing_background(self, repo_id: int):
        """
        Helper to run indexing in a fire-and-forget background task.

        NOTE: This is an async method but should NOT be awaited by caller.
        Use asyncio.create_task(run_indexing_background(...)) instead.
        """
        asyncio.create_task(self._dispatch_repo_index(repo_id))


# Global Instance
indexing_manager = IndexingManager()
