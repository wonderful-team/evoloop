import logging
import os

from app.domain.codebase.indexing.service import IndexingService
from app.domain.project.service import project_context_manager
from app.infrastructure.external.evocloud import evocloud_client

logger = logging.getLogger(__name__)


class ProjectSyncService:
    """
    Service responsible for synchronizing local project state with the Cloud (EvoCloud).
    Implements a "Local-First" strategy ensuring robustness against network failures.
    """

    def __init__(self):
        self._indexing_service = IndexingService()

    async def handle_project_created(self, path: str):
        """
        Handle creation of a new local project directory.
        """
        repo_name = os.path.basename(path)
        logger.info(f"[ProjectSync] Detected new project at: {path}")

        # 1. Check for Existing Link (Re-import case)
        # We first check if this path is already known to the system via Context/API scan.
        project_id = await self._resolve_existing_project_id(path)

        # 2. Local-First Creation: Ensure Repository record exists immediately
        # If we found an ID, great. If not, we create with None (Pending).
        try:
            repo = await self._indexing_service.get_or_create_repo(
                path,
                repo_name,
                project_id=project_id
            )
            # If newly created and project_id is None, sync_status will be PENDING by default/logic
            if repo.project_id:
                logger.info(f"[ProjectSync] Linked to existing Project ID {repo.project_id}")
            else:
                logger.info("[ProjectSync] Created local record (Pending Cloud Sync)")

        except Exception as e:
            logger.error(f"[ProjectSync] Failed to create local repository record: {e}")
            return

        # 3. Cloud Sync (Async + Retry via Celery)
        if not repo.project_id:
            logger.info(f"[ProjectSync] Dispatching background sync for '{repo_name}'...")
            from app.domain.project.sync_tasks import sync_project_to_cloud_task

            # Dispatch task
            # We use apply_async to ensure it's queued
            try:
                sync_project_to_cloud_task.delay(repo.id)
                logger.info(f"[ProjectSync] Sync task queued for Repo ID {repo.id}")
            except Exception as e:
                logger.error(f"[ProjectSync] Failed to queue sync task: {e}")

        # 4. Start Indexing (Background/Celery)
        # We use run_indexing_background which dispatches to Celery if possible.
        # This prevents blocking the main process and "massive logs" during startup reconciliation.
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.start_watching(path, repo.id)
            await indexing_manager.run_indexing_background(repo.id)
        except Exception as e:
            logger.error(f"Failed to trigger background indexing for {path}: {e}")

    async def handle_project_deleted(self, path: str):
        """
        Handle deletion of a local project directory.
        """
        repo_name = os.path.basename(path)

        # 1. Stop Watching
        try:
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.stop_watching(path)
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to stop watching {path}: {e}")

        # 2. Update Local State (Disconnect)
        # We don't delete the Cloud project.
        try:
            repo = await self._indexing_service.get_repo_by_path(path)
            if repo:
                async with self._indexing_service.session_factory() as session:
                    r = await session.get(type(repo), repo.id)
                    if r:
                        r.sync_status = "DISCONNECTED"
                        # We might check if we should clear local_path to avoid confusion?
                        # Or keep it as "Last Known Location".
                        # Let's keep it but mark disconnected.
                        session.add(r)
                        await session.commit()
                logger.info(f"[ProjectSync] Project {repo_name} marked as DISCONNECTED.")
        except Exception as e:
            logger.error(f"[ProjectSync] Error updating disconnect status: {e}")

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

            # 2. Stop Old Watch
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.stop_watching(src_path)

            # 3. Update Cloud (Best Effort)
            if repo.project_id:
                try:
                    await evocloud_client.update_project(
                        project_id=repo.project_id,
                        name=new_name,
                        path=dest_path
                    )
                    logger.info("[ProjectSync] Cloud Project Updated.")
                except Exception as e:
                    logger.error(f"[ProjectSync] Cloud Update Failed: {e}")

            # 4. Update Local Record
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

            # 5. Start New Watch
            await indexing_manager.start_watching(dest_path, repo.id)

        except Exception as e:
            logger.error(f"[ProjectSync] Move handling failed: {e}")

    async def _resolve_existing_project_id(self, path: str) -> int | None:
        """Try to resolve Project ID from Context/Settings/Cache."""
        try:
            projects = await project_context_manager.scan_projects()
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
        """
        if not root_path or not os.path.exists(root_path):
            logger.warning(f"[ProjectSync] Root path {root_path} invalid. Skipping reconciliation.")
            return

        logger.info(f"[ProjectSync] Starting Reconciliation on {root_path}...")

        # 1. Scan Filesystem (Dirs only)
        # Exclude hidden folders like .evoloop, .git
        fs_projects = set()
        try:
            for entry in os.scandir(root_path):
                if entry.is_dir() and not entry.name.startswith("."):
                    fs_projects.add(entry.path)
        except Exception as e:
            logger.error(f"[ProjectSync] FS Scan failed: {e}")
            return

        # 2. Get Known Projects (Local DB)
        # We use IndexingService to get all local repositories.
        # Note: We trust local DB "local_path" as truth for what System thinks exists.
        known_projects_map = {}  # path -> repo
        try:
            repos = await self._indexing_service.get_all_repos()
            for r in repos:
                if r.local_path:
                    abs_p = os.path.abspath(r.local_path)
                    known_projects_map[abs_p] = r
        except Exception as e:
            logger.error(f"[ProjectSync] DB Scan failed: {e}")
            # If DB fails, abort to be safe (don't delete everything).
            return

        # 3. Detect Changes
        known_paths = set(known_projects_map.keys())
        # Normalize FS paths
        fs_paths = {os.path.abspath(p) for p in fs_projects}

        # A. New Projects (In FS, Not in DB)
        new_paths = fs_paths - known_paths
        for p in new_paths:
            logger.info(f"[ProjectSync] Found offline creation: {p}")
            await self.handle_project_created(p)

        # A.2 Retry Pending Projects
        # Projects that exist locally (FS & DB) but failed to sync to Cloud previously.
        for p in known_paths:
            if p in fs_paths:
                repo = known_projects_map[p]
                if repo.sync_status == "PENDING_CREATION":
                    logger.info(f"[ProjectSync] Retrying sync for pending project: {p}")
                    # Re-use handle_project_created logic which handles "Already exists" checks smartly
                    # But handle_project_created does get_or_create.
                    # Since it exists, it will get it. Then check if project_id is missing.
                    # Then try sync. This matches our need perfectly.
                    await self.handle_project_created(p)

        # B. Deleted Projects (In DB, Not in FS)
        # Only verify repos that are supposed to be inside this root_path?
        # Yes, if we have repos elsewhere, this watcher shouldn't touch them.
        abs_root = os.path.abspath(root_path)

        missing_paths = []
        for p in known_paths:
            # Check if this project belongs to the monitored root
            # e.g. /projects/foo is inside /projects
            if p.startswith(abs_root) and p not in fs_paths:
                # Double check it's not actually there (case sensitivity?)
                if not os.path.exists(p):
                    missing_paths.append(p)

        for p in missing_paths:
            # Check status first. If already DISCONNECTED, skip.
            repo = known_projects_map[p]
            if repo.sync_status != "DISCONNECTED":
                logger.info(f"[ProjectSync] Found offline deletion: {p}")
                await self.handle_project_deleted(p)

        logger.info(f"[ProjectSync] Reconciliation Complete. New: {len(new_paths)}, Missing: {len(missing_paths)}")


# Global Instance
project_sync_service = ProjectSyncService()
