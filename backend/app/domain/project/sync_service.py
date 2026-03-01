import logging
import os

from sqlalchemy import select

from app.core.events import system_bus
from app.core.evocloud import evocloud_manager
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models.codebase import Repository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class ProjectSyncService:
    """
    Service responsible for synchronizing local project state with the Cloud (EvoCloud).
    Implements a "Local-First" strategy ensuring robustness against network failures.

    Project Import Flow:
    1. File system detection -> Create Repository with sync_status="DETECTED"
    2. Publish NewProjectDetectedEvent -> Frontend shows notification
    3. User clicks "Import" -> import_project() updates status, starts indexing
    4. User clicks "Ignore" -> ignore_project() marks as ignored
    """

    def __init__(self):
        self._indexing_service = IndexingService()

    async def handle_project_created(self, path: str):
        """
        Handle creation of a new local project directory.

        Creates a Repository record with DETECTED status and publishes
        NewProjectDetectedEvent for frontend notification.
        Indexing is NOT started until user confirms import.
        """
        repo_name = os.path.basename(path)
        logger.info(f"[ProjectSync] Detected new project at: {path}")

        # Check if should auto-ignore (system directories)
        if self._should_auto_ignore(path):
            logger.info(f"[ProjectSync] Auto-ignoring system directory: {path}")
            return

        # Check for existing record
        existing = await self._indexing_service.get_repo_by_path(path)
        if existing:
            logger.info(f"[ProjectSync] Project already exists: {path}")
            return

        try:
            # Create Repository with DETECTED status (awaiting user confirmation)
            async with AsyncSessionLocal() as session:
                repo = Repository(
                    name=repo_name,
                    url="local",
                    local_path=path,
                    sync_status="DETECTED",
                    detected_at=utcnow(),
                    project_id=None,
                )
                session.add(repo)
                await session.commit()
                await session.refresh(repo)

            logger.info(f"[ProjectSync] Project '{repo_name}' created with status DETECTED (ID: {repo.id})")

            # Publish NewProjectDetectedEvent for frontend notification
            # IndexingManager should NOT subscribe to this event
            try:
                from app.domain.project.events import NewProjectDetectedEvent

                await system_bus.publish(NewProjectDetectedEvent(
                    repo_id=repo.id,
                    path=path,
                    name=repo_name,
                    detected_at=repo.detected_at
                ))
            except Exception as e:
                logger.error(f"[ProjectSync] Failed to publish NewProjectDetectedEvent: {e}")

        except Exception as e:
            logger.error(f"[ProjectSync] Failed to create repository record: {e}")

    async def import_project(self, repo_id: int) -> Repository:
        """
        Import a detected project (user confirmed).

        This method:
        1. Updates Repository status to PENDING_CREATION
        2. Publishes ProjectCreatedEvent to trigger indexing
        3. Dispatches cloud sync task

        Args:
            repo_id: The Repository ID to import

        Returns:
            The updated Repository object

        Raises:
            ValueError: If repository not found or already imported
        """
        async with AsyncSessionLocal() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status not in ["DETECTED", "IGNORED"]:
                logger.warning(f"[ProjectSync] Project {repo_id} already imported (status: {repo.sync_status})")
                return repo

            # Update status
            repo.sync_status = "PENDING_CREATION"
            repo.imported_at = utcnow()
            await session.commit()

            logger.info(f"[ProjectSync] Project '{repo.name}' imported by user (ID: {repo_id})")

        # Publish ProjectCreatedEvent to trigger indexing
        # IndexingManager subscribes to this event
        try:
            from app.domain.project.events import ProjectCreatedEvent

            await system_bus.publish(ProjectCreatedEvent(
                path=repo.local_path,
                repo_id=repo.id,
                project_id=repo.project_id,
                project_name=repo.name
            ))
            logger.info(f"[ProjectSync] Published ProjectCreatedEvent for {repo.name}")
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectCreatedEvent: {e}")

        # Dispatch cloud sync task
        try:
            from app.domain.project.sync_tasks import sync_project_to_cloud_task
            sync_project_to_cloud_task.delay(repo.id)
            logger.info(f"[ProjectSync] Cloud sync task queued for Repo ID {repo.id}")
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to queue sync task: {e}")

        return repo

    async def ignore_project(self, repo_id: int):
        """
        Ignore a detected project (user chose not to import).

        Marks the repository as IGNORED. Can be re-imported later via unignore_project.
        """
        async with AsyncSessionLocal() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status != "DETECTED":
                logger.warning(f"[ProjectSync] Cannot ignore project with status: {repo.sync_status}")
                return

            repo.sync_status = "IGNORED"
            await session.commit()

            logger.info(f"[ProjectSync] Project '{repo.name}' ignored by user (ID: {repo_id})")

    async def unignore_project(self, repo_id: int) -> Repository:
        """
        Restore an ignored project to detected status (can be imported).
        """
        async with AsyncSessionLocal() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status != "IGNORED":
                logger.warning(f"[ProjectSync] Project {repo_id} is not ignored (status: {repo.sync_status})")
                return repo

            repo.sync_status = "DETECTED"
            await session.commit()

            logger.info(f"[ProjectSync] Project '{repo.name}' restored to DETECTED (ID: {repo_id})")
            return repo

    async def get_detected_projects(self) -> list[Repository]:
        """Get all projects with DETECTED status (awaiting user confirmation)."""
        async with AsyncSessionLocal() as session:
            stmt = select(Repository).where(
                Repository.sync_status == "DETECTED"
            ).order_by(Repository.detected_at.desc())

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_ignored_projects(self) -> list[Repository]:
        """Get all projects with IGNORED status."""
        async with AsyncSessionLocal() as session:
            stmt = select(Repository).where(
                Repository.sync_status == "IGNORED"
            ).order_by(Repository.detected_at.desc())

            result = await session.execute(stmt)
            return list(result.scalars().all())

    def _should_auto_ignore(self, path: str) -> bool:
        """Check if a directory should be automatically ignored."""
        name = os.path.basename(path)

        # Hidden directories
        if name.startswith("."):
            return True

        # System/build directories to ignore
        ignored_names = {
            "node_modules",
            "__pycache__",
            ".git",
            ".svn",
            ".hg",
            "dist",
            "build",
            "target",
            "vendor",
            "tmp",
            "temp",
            "out",
            "bin",
            "obj",
            ".next",
            ".nuxt",
            ".venv",
            "venv",
            "env",
            ".idea",
            ".vscode",
        }

        if name in ignored_names:
            return True

        # Check for common non-project prefixes
        ignored_prefixes = ("~", "_", ".")
        if name.startswith(ignored_prefixes):
            return True

        return False

    async def handle_project_deleted(self, path: str):
        """
        Handle deletion of a local project directory.
        """
        repo_name = os.path.basename(path)
        repo_id = None
        project_id = None

        # 1. Update Local State (Disconnect)
        # We don't delete the Cloud project.
        try:
            repo = await self._indexing_service.get_repo_by_path(path)
            if repo:
                repo_id = repo.id
                project_id = repo.project_id
                async with self._indexing_service.session_factory() as session:
                    r = await session.get(type(repo), repo.id)
                    if r:
                        r.sync_status = "DISCONNECTED"
                        session.add(r)
                        await session.commit()
                logger.info(f"[ProjectSync] Project {repo_name} marked as DISCONNECTED.")
        except Exception as e:
            logger.error(f"[ProjectSync] Error updating disconnect status: {e}")

        # 2. Publish ProjectDeletedEvent (decoupled)
        # IndexingManager will subscribe and stop watching
        try:
            from app.domain.project.events import ProjectDeletedEvent

            await system_bus.publish(ProjectDeletedEvent(
                path=path,
                repo_id=repo_id or 0,
                project_id=project_id
            ))
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectDeletedEvent: {e}")

    async def handle_project_moved(self, src_path: str, dest_path: str):
        """
        Handle move/rename of a local project.
        """
        new_name = os.path.basename(dest_path)
        logger.info(f"[ProjectSync] Detected Move: {src_path} -> {dest_path}")

        try:
            # 1. Find Repo
            repo = await self._indexing_service.get_repo_by_path(src_path)
            if not repo:
                logger.warning(f"[ProjectSync] Move source {src_path} not found. Treating as New Creation.")
                await self.handle_project_created(dest_path)
                return

            # 2. If project is DETECTED or IGNORED, just update the path
            if repo.sync_status in ["DETECTED", "IGNORED"]:
                async with self._indexing_service.session_factory() as session:
                    r = await session.get(Repository, repo.id)
                    if r:
                        r.local_path = dest_path
                        r.name = new_name
                        session.add(r)
                        await session.commit()
                logger.info(f"[ProjectSync] Updated path for {repo.sync_status} project: {dest_path}")
                return

            # 3. Stop Old Watch (for imported projects)
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.stop_watching(src_path)

            # 4. Update Cloud (Best Effort)
            if repo.project_id:
                try:
                    await evocloud_manager.api.update_project(
                        project_id=repo.project_id,
                        name=new_name,
                        path=dest_path
                    )
                    logger.info("[ProjectSync] Cloud Project Updated.")
                except Exception as e:
                    logger.error(f"[ProjectSync] Cloud Update Failed: {e}")

            # 5. Update Local Record
            async with self._indexing_service.session_factory() as session:
                r = await session.get(type(repo), repo.id)
                if r:
                    r.local_path = dest_path
                    r.name = new_name
                    # If it was disconnected, moving it might reconnect it?
                    if r.sync_status == "DISCONNECTED":
                        r.sync_status = "SYNCED"
                    session.add(r)
                    await session.commit()

            # 6. Start New Watch
            await indexing_manager.start_watching(dest_path, repo.id)

        except Exception as e:
            logger.error(f"[ProjectSync] Move handling failed: {e}")

    async def _resolve_existing_project_id(self, path: str) -> int | None:
        """Try to resolve Project ID from Context/Settings/Cache."""
        try:
            projects = await evocloud_manager.scan_projects()
            abs_path = os.path.abspath(path)
            for p in projects:
                if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                    return p.get("id")
        except Exception:
            pass
        return None

    async def reconcile_projects(self, root_path: str):
        """
        Reconcile local filesystem projects with system state (DB/Cloud).
        Handles creation/deletion that occurred while service was offline.

        Modified: Only starts indexing for already-imported projects.
        Newly detected projects are created with DETECTED status.
        """
        if not root_path or not os.path.exists(root_path):
            logger.warning(f"[ProjectSync] Root path {root_path} invalid. Skipping reconciliation.")
            return

        logger.info(f"[ProjectSync] Starting Reconciliation on {root_path}...")

        # 1. Scan Filesystem (Direct subdirectories only)
        fs_projects = set()
        try:
            for entry in os.scandir(root_path):
                if entry.is_dir() and not entry.name.startswith("."):
                    # Use absolute path for consistency
                    fs_projects.add(os.path.abspath(entry.path))
        except Exception as e:
            logger.error(f"[ProjectSync] FS Scan failed: {e}")
            return

        # 2. Get Known Projects (Local DB)
        known_projects_map = {}
        try:
            repos = await self._indexing_service.get_all_repos()
            for r in repos:
                if r.local_path:
                    abs_p = os.path.abspath(r.local_path)
                    known_projects_map[abs_p] = r
        except Exception as e:
            logger.error(f"[ProjectSync] DB Scan failed: {e}")
            return

        # 3. Detect Changes
        known_paths = set(known_projects_map.keys())
        fs_paths = {os.path.abspath(p) for p in fs_projects}

        # A. New Projects (In FS, Not in DB)
        # Create as DETECTED, don't start indexing
        new_paths = fs_paths - known_paths
        for p in new_paths:
            logger.info(f"[ProjectSync] Found offline creation: {p}")
            await self.handle_project_created(p)

        # B. Restored Projects (In DB as DISCONNECTED, but now in FS)
        for p in known_paths & fs_paths:
            repo = known_projects_map[p]
            if repo.sync_status == "DISCONNECTED":
                logger.info(f"[ProjectSync] Restoring disconnected project: {p}")
                try:
                    async with AsyncSessionLocal() as session:
                        r = await session.get(Repository, repo.id)
                        if r:
                            # If it has project_id, it was likely SYNCED. 
                            # If not, it was DETECTED or PENDING_CREATION.
                            if r.project_id:
                                r.sync_status = "SYNCED"
                            else:
                                r.sync_status = "DETECTED"
                            session.add(r)
                            await session.commit()
                            # Update map for subsequent steps
                            repo.sync_status = r.sync_status
                except Exception as e:
                    logger.error(f"[ProjectSync] Failed to restore project {p}: {e}")

        # C. Retry Pending Cloud Sync for Imported Projects
        for p in known_paths:
            if p in fs_paths:
                repo = known_projects_map[p]
                # Retry cloud sync for imported projects that failed
                if repo.sync_status == "PENDING_CREATION":
                    logger.info(f"[ProjectSync] Retrying cloud sync for: {p}")
                    try:
                        from app.domain.project.sync_tasks import sync_project_to_cloud_task
                        sync_project_to_cloud_task.delay(repo.id)
                    except Exception as e:
                        logger.error(f"[ProjectSync] Failed to queue retry: {e}")

        # C. Restart watching for imported projects (SYNCED or PENDING_CREATION)
        imported_statuses = {"SYNCED", "PENDING_CREATION"}
        imported_paths = {
            p for p in known_paths
            if known_projects_map[p].sync_status in imported_statuses
        }

        for p in imported_paths & fs_paths:
            repo = known_projects_map[p]
            logger.info(f"[ProjectSync] Restarting watcher for imported project: {p}")
            try:
                from app.domain.codebase.indexing.manager import indexing_manager

                # Check if already watching
                if p not in indexing_manager._watchers:
                    await indexing_manager.start_watching(p, repo.id)
            except Exception as e:
                logger.error(f"[ProjectSync] Failed to restart watcher for {p}: {e}")

        # D. Deleted Projects (In DB, Not in FS)
        abs_root = os.path.abspath(root_path)
        missing_paths = []
        for p in known_paths:
            if p.startswith(abs_root) and p not in fs_paths:
                if not os.path.exists(p):
                    missing_paths.append(p)

        for p in missing_paths:
            repo = known_projects_map[p]
            if repo.sync_status != "DISCONNECTED":
                logger.info(f"[ProjectSync] Found offline deletion: {p}")
                await self.handle_project_deleted(p)

        logger.info(
            f"[ProjectSync] Reconciliation Complete. "
            f"New: {len(new_paths)}, "
            f"Imported Restarted: {len(imported_paths & fs_paths)}, "
            f"Missing: {len(missing_paths)}"
        )


# Global Instance
project_sync_service = ProjectSyncService()
