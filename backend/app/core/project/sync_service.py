import asyncio
import logging
import os

from sqlalchemy import select

from app.core.evocloud import evocloud_manager
from app.core.file import is_ignored_path
from app.core.hitl.policies import DEFAULT_SENSITIVE_PATTERNS
from app.core.project import cache as project_cache
from app.core.project.utils import read_project_json, write_project_json
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database import session_scope
from app.models.codebase import Repository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class ProjectSyncService:
    """
    Service responsible for synchronizing local project state with the Cloud (EvoCloud).
    Implements a "Local-First" strategy ensuring robustness against network failures.
    """

    def __init__(self):
        self._indexing_service = IndexingService()

    async def sync_cloud_project(self, start_watchers: bool = True) -> None:
        """
        Sync the active project to local workspace on app start.

        Local-first strategy:
        1. Scan local WORKSPACE_ROOT for projects (via .evoloop/project.json).
        2. If there is a persisted active project_id, prefer that.
        3. Otherwise use the cloud's current project_id only as a hint.
        4. If the hinted project does not exist locally, do not auto-switch;
           log a clear message and wait for user action.
        5. Never use the cloud's external_path directly as the local path.

        Args:
            start_watchers: When False (worker context), skip starting the
                in-process file watcher, which must live in the API process.
        """
        try:
            from app.core.context import thread_context_store
            from app.core.project.local_index import local_project_index
            from app.domain.codebase.indexing.manager import indexing_manager
            from app.infrastructure.config.service import SystemConfigService

            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            logger.info(f"[ProjectSync] sync_cloud_project started. WORKSPACE_ROOT={workspace_root}")
            if not workspace_root:
                logger.info("[ProjectSync] WORKSPACE_ROOT not configured. Skipping cloud project sync.")
                return

            # Local-first: build local index before talking to cloud
            local_index = local_project_index.refresh(workspace_root)
            logger.info(f"[ProjectSync] Local project index: {local_index}")
            if not local_index:
                logger.info("[ProjectSync] No local projects found. Skipping cloud project sync.")
                return

            # Sync local projects' external_source to cloud with the active device key
            try:
                from app.core.identity import identity_service

                device_key = await identity_service.store.get_device_key()
                if device_key:
                    logger.info(f"[ProjectSync] Aligning local projects with device key: {device_key}")
                    pids = list(local_index.keys())
                    results = await asyncio.gather(
                        *(self._align_project_source(pid, device_key) for pid in pids),
                        return_exceptions=True,
                    )
                    for pid, result in zip(pids, results, strict=False):
                        if isinstance(result, Exception):
                            logger.warning(f"[ProjectSync] Failed to update project {pid} source to {device_key}: {result}")
                        else:
                            logger.info(f"[ProjectSync] Aligned project {pid} source to {device_key} in cloud")
            except Exception as e:
                logger.warning(f"[ProjectSync] Failed to run local project source alignment: {e}")

            # Prefer the persisted active project (user's last explicit choice)
            active_project_id = thread_context_store.get_active_project("default")
            selected_project_id = None
            if active_project_id is not None and active_project_id in local_index:
                selected_project_id = active_project_id
                logger.info(
                    f"[ProjectSync] Using persisted active project: project_id={selected_project_id}, "
                    f"path={local_index[selected_project_id].path}"
                )

            # Cloud hint: only advisory, never authoritative over local path
            if selected_project_id is None:
                res = await evocloud_manager.api.get_current_project()
                logger.info(f"[ProjectSync] get_current_project response: {res}")
                cloud_project_id = None
                if res and res.get("code") == 0:
                    project_data = res.get("data") or {}
                    cloud_project_id = project_data.get("project_id")
                    cloud_external_path = project_data.get("external_path")
                    logger.info(
                        f"[ProjectSync] Cloud current project hint: "
                        f"project_id={cloud_project_id}, "
                        f"external_path={cloud_external_path!r} "
                        f"(used for reference only, not as local path)"
                    )
                else:
                    logger.info(
                        "[ProjectSync] No current project hint from cloud: "
                        f"{res.get('message') if res else 'Empty response'}."
                    )

                if cloud_project_id is not None and cloud_project_id in local_index:
                    selected_project_id = cloud_project_id
                    logger.info(
                        f"[ProjectSync] Cloud hint matched local project: "
                        f"project_id={selected_project_id}, path={local_index[selected_project_id].path}"
                    )
                elif cloud_project_id is not None:
                    logger.warning(
                        f"[ProjectSync] Cloud project_id={cloud_project_id} not found locally. "
                        "Ignoring cloud hint to keep local path as truth source."
                    )

            if selected_project_id is None:
                logger.info(
                    "[ProjectSync] No active or cloud-hinted project matches local projects. "
                    "Waiting for user to select a project."
                )
                return

            entry = local_index.get(selected_project_id)
            local_path = entry.path if entry else None
            if not local_path or not os.path.exists(local_path):
                logger.warning(f"[ProjectSync] Selected local path does not exist: {local_path}")
                return

            is_ignored = await project_cache.is_path_ignored(local_path)
            if not is_ignored:
                existing_repo = await self._indexing_service.get_repo_by_path(local_path)
                if existing_repo and existing_repo.sync_status == "IGNORED":
                    is_ignored = True

            if is_ignored:
                logger.info(f"[ProjectSync] Skipping cloud project sync for ignored path: {local_path}")
                return

            logger.info(f"[ProjectSync] Synced active project: {local_path}")
            thread_context_store.set_working_directory("default", local_path)

            repo_name = os.path.basename(local_path)
            repo = await self._indexing_service.get_or_create_repo(local_path, repo_name)
            logger.info(
                f"[ProjectSync] Local repo: repo_id={repo.id if repo else None}, "
                f"project_id={repo.project_id if repo else None}, "
                f"sync_status={repo.sync_status if repo else None}"
            )
            if repo.project_id:
                write_project_json(local_path, {"project_id": repo.project_id, "repo_id": repo.id})
            if start_watchers:
                await indexing_manager.start_watching(local_path, repo.id)

        except Exception as e:
            logger.warning(f"[ProjectSync] Error syncing cloud project: {e}", exc_info=True)

    @staticmethod
    async def _align_project_source(project_id: int, device_key: str) -> None:
        """Point a cloud project's external source at the active device."""
        await evocloud_manager.api.update_project(
            project_id=project_id, source=device_key
        )

    async def handle_project_created(self, path: str):
        """
        Handle recovery/auto-link of a local project directory if it already has project metadata.
        """
        repo_name = os.path.basename(path)
        abs_path = os.path.abspath(path)
        logger.info(f"[ProjectSync] Checking metadata for project at: {path}")

        if is_ignored_path(path):
            return

        existing = await self._indexing_service.get_repo_by_path(path)
        if existing:
            return

        # Recovery: check if .evoloop/project.json exists (directory was moved while offline)
        project_json = read_project_json(abs_path)
        if project_json and project_json.get("project_id") and project_json["project_id"] > 0:
            recovered_project_id = int(project_json["project_id"])
            logger.info(
                f"[ProjectSync] Found .evoloop/project.json with project_id={recovered_project_id}. "
                f"Recovering cloud link for directory: {path}"
            )
            try:
                async with session_scope() as session:
                    # Check if a Repository with this project_id already exists
                    stmt = select(Repository).where(
                        Repository.project_id == recovered_project_id,
                        Repository.sync_status.notin_(["IGNORED", "DISCONNECTED"]),
                    )
                    result = await session.execute(stmt)
                    existing_repo = result.scalars().first()

                    if existing_repo:
                        existing_repo.local_path = path
                        existing_repo.relative_path = repo_name
                        existing_repo.sync_status = "SYNCED"
                        await session.commit()
                        logger.info(
                            f"[ProjectSync] Updated existing Repository {existing_repo.id} "
                            f"to new path {path} (project_id={recovered_project_id})"
                        )
                        write_project_json(abs_path, {
                            "project_id": recovered_project_id,
                            "repo_id": existing_repo.id,
                        })
                        await self._update_cloud_project_path(recovered_project_id, abs_path)
                        await self._trigger_auto_indexing(existing_repo, path)
                        return
                    else:
                        repo = Repository(
                            name=repo_name,
                            url="local",
                            local_path=path,
                            relative_path=repo_name,
                            sync_status="SYNCED",
                            indexing_status="pending",
                            detected_at=utcnow(),
                            imported_at=utcnow(),
                            project_id=recovered_project_id,
                        )
                        session.add(repo)
                        await session.commit()
                        await session.refresh(repo)
                        logger.info(
                            f"[ProjectSync] Created new Repository {repo.id} recovering "
                            f"project_id={recovered_project_id} at path {path}"
                        )
                        write_project_json(abs_path, {
                            "project_id": recovered_project_id,
                            "repo_id": repo.id,
                        })
                        await self._update_cloud_project_path(recovered_project_id, abs_path)
                        await self._trigger_auto_indexing(repo, path)
                        return
            except Exception as e:
                logger.warning(f"[ProjectSync] Failed to recover project from project.json: {e}")

    async def import_project_by_path(self, path: str, workspace_root: str, name: str | None = None) -> Repository:
        """
        Import an existing local directory under workspace_root as a project.
        """
        from app.core.project.path_validator import validate_project_path

        abs_path = os.path.realpath(path)
        if not os.path.isdir(abs_path):
            raise ValueError(f"Directory does not exist: {abs_path}")

        await validate_project_path(abs_path, workspace_root)

        repo_name = name or os.path.basename(abs_path)

        async with session_scope() as session:
            stmt = select(Repository).where(Repository.local_path == abs_path)
            result = await session.execute(stmt)
            repo = result.scalars().first()

            if repo:
                if repo.sync_status in ["SYNCED", "PENDING_CREATION"]:
                    raise ValueError(f"Project is already registered at this path: '{repo.name}'")
                
                # Restore previously ignored or disconnected project
                repo.sync_status = "PENDING_CREATION"
                repo.indexing_status = "pending"
                repo.imported_at = utcnow()
                repo.name = repo_name
                session.add(repo)
                await session.commit()
                await session.refresh(repo)
            else:
                repo = Repository(
                    name=repo_name,
                    url="local",
                    local_path=abs_path,
                    relative_path=os.path.relpath(abs_path, workspace_root),
                    sync_status="PENDING_CREATION",
                    indexing_status="pending",
                    detected_at=utcnow(),
                    imported_at=utcnow(),
                    project_id=None,
                )
                session.add(repo)
                await session.commit()
                await session.refresh(repo)

        # Create/update project.json metadata
        meta_dir = os.path.join(abs_path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)

        project_json = read_project_json(abs_path) or {}
        if not project_json:
            project_json = {
                "name": repo_name,
                "description": f"Imported from {abs_path}",
                "project_id": None,
                "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
                "authorized_paths": [],
            }

        cloud_project_id = project_json.get("project_id")

        # Sync to Cloud
        try:
            res = await evocloud_manager.api.create_project(
                name=repo_name,
                description=f"Imported from {abs_path}",
                path=abs_path,
            )
            if res.get("code") == 0:
                cloud_project_id = int(res["data"]["project_id"])
                async with session_scope() as session:
                    db_repo = await session.get(Repository, repo.id)
                    if db_repo:
                        db_repo.project_id = cloud_project_id
                        db_repo.sync_status = "SYNCED"
                        session.add(db_repo)

                evocloud_manager.invalidate_projects_cache()
                logger.info(f"[ProjectSync] Imported project synced to cloud (ID: {cloud_project_id})")
            else:
                logger.warning(f"[ProjectSync] Cloud sync failed: {res.get('message')}")
        except Exception as e:
            logger.error(f"[ProjectSync] Cloud sync failed: {e}")

        # Update metadata file
        write_project_json(abs_path, {
            "project_id": cloud_project_id or project_json.get("project_id"),
            "repo_id": repo.id
        })

        # Publish event
        try:
            from app.core.project.event.publishers import publish_project_created

            await publish_project_created(
                path=abs_path,
                repo_id=repo.id,
                project_id=cloud_project_id or project_json.get("project_id"),
                project_name=repo_name,
            )
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectCreatedEvent: {e}")

        # Start watching
        from app.domain.codebase.indexing.manager import indexing_manager

        await indexing_manager.start_watching(abs_path, repo.id)

        return repo

    async def _update_cloud_project_path(self, project_id: int, new_path: str) -> None:
        """Update cloud external_path after a directory move."""
        try:
            from app.core.identity import identity_service

            device_key = await identity_service.store.get_device_key()
            if device_key:
                await evocloud_manager.api.update_project(
                    project_id=project_id,
                    source=device_key,
                )
                logger.info(
                    f"[ProjectSync] Updated cloud project {project_id} source after path move to {new_path}"
                )
        except Exception as e:
            logger.warning(f"[ProjectSync] Failed to update cloud path for project {project_id}: {e}")

    async def _find_matching_cloud_project(self, repo_name: str, local_path: str) -> dict | None:
        """
        Find matching cloud project by local path.
        """
        try:
            cloud_projects = await evocloud_manager.scan_projects()
            abs_local_path = os.path.abspath(local_path)

            for project in cloud_projects:
                cloud_path = project.get("path", "")
                if cloud_path and os.path.abspath(cloud_path) == abs_local_path:
                    logger.info(f"[ProjectSync] Matched cloud project by path: {abs_local_path}")
                    return project

            logger.info(f"[ProjectSync] No cloud project matched local path: {abs_local_path}")
            return None
        except Exception as e:
            logger.warning(f"[ProjectSync] Failed to scan cloud projects: {e}. Treating as new project.")
            return None

    async def _trigger_auto_indexing(self, repo: Repository, path: str):
        """
        Auto-trigger indexing for auto-linked projects.
        """
        try:
            from app.core.project.event.publishers import publish_project_created

            # Publish ProjectCreatedEvent to trigger indexing
            await publish_project_created(
                path=path,
                repo_id=repo.id,
                project_id=repo.project_id,
                project_name=repo.name,
            )
            logger.info(f"[ProjectSync] Auto-triggered indexing for '{repo.name}' (Repo ID: {repo.id})")

            # Start watching
            from app.domain.codebase.indexing.manager import indexing_manager

            await indexing_manager.start_watching(path, repo.id)

        except Exception as e:
            logger.error(f"[ProjectSync] Failed to auto-trigger indexing for '{repo.name}': {e}")

    async def handle_project_deleted(self, path: str):
        """
        Handle deletion of a local project directory.
        """
        repo_name = os.path.basename(path)

        try:
            async with session_scope() as session:
                stmt = select(Repository).where(Repository.local_path == path)
                result = await session.execute(stmt)
                all_repos = result.scalars().all()

                if not all_repos:
                    logger.debug(f"[ProjectSync] No repository records found for path: {path}")
                    return

                to_disconnect = [r for r in all_repos if r.sync_status != "DISCONNECTED"]
                if not to_disconnect:
                    logger.debug(f"[ProjectSync] Project {repo_name} already marked as DISCONNECTED. Skipping.")
                    return

                for r in to_disconnect:
                    db_repo = await session.get(Repository, r.id)
                    if db_repo:
                        db_repo.sync_status = "DISCONNECTED"

                repo_id = to_disconnect[0].id
                project_id = to_disconnect[0].project_id
                logger.info(f"[ProjectSync] Project {repo_name} marked as DISCONNECTED.")

        except Exception as e:
            logger.error(f"[ProjectSync] Error updating disconnect status for {path}: {e}")
            return

        try:
            from app.core.project.event.publishers import publish_project_deleted

            await publish_project_deleted(
                path=path,
                repo_id=repo_id or 0,
                project_id=project_id
            )
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectDeletedEvent for {path}: {e}")

    async def handle_project_moved(self, src_path: str, dest_path: str):
        """
        Handle move/rename of a local project.
        """
        new_name = os.path.basename(dest_path)
        logger.info(f"[ProjectSync] Detected Move: {src_path} -> {dest_path}")

        repo = await self._indexing_service.get_repo_by_path(src_path)
        if not repo:
            logger.warning(f"[ProjectSync] Move source {src_path} not found. Skipping.")
            return

        # Stop Old Watch (for imported projects)
        from app.domain.codebase.indexing.manager import indexing_manager

        await indexing_manager.stop_watching(src_path)

        # Update Cloud
        if repo.project_id:
            try:
                await evocloud_manager.api.update_project(
                    project_id=repo.project_id,
                    name=new_name,
                    path=dest_path
                )
                logger.info("[ProjectSync] Cloud Project Updated.")
                evocloud_manager.invalidate_projects_cache()
            except Exception as e:
                logger.error(f"[ProjectSync] Cloud Update Failed: {e}")

        # Update Local Record
        async with self._indexing_service.session_factory() as session:
            r = await session.get(type(repo), repo.id)
            if r:
                r.local_path = dest_path
                r.relative_path = new_name
                r.name = new_name
                if r.sync_status == "DISCONNECTED":
                    r.sync_status = "SYNCED"
                session.add(r)

        # Start New Watch
        await indexing_manager.start_watching(dest_path, repo.id)

    async def _resolve_existing_project_id(self, path: str) -> int | None:
        """Try to resolve Project ID from Cache."""
        try:
            projects = await evocloud_manager.scan_projects()
            abs_path = os.path.abspath(path)
            for p in projects:
                if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                    return p.get("id")
        except Exception as e:
            logger.debug("Suppressed error: %s", e)
        return None

    async def reconcile_projects(self, root_path: str, force: bool = False):
        """
        Reconcile known local projects in DB with the filesystem.
        Restart watchers for imported projects.
        """
        if not root_path or not os.path.exists(root_path):
            logger.warning(
                f"[ProjectSync] Root path {root_path} invalid. Skipping reconciliation."
            )
            return

        logger.info(f"[ProjectSync] Starting Reconciliation on {root_path}...")

        # 1. Get Known Projects (Local DB)
        known_projects_map = {}
        try:
            repos = await self._indexing_service.get_all_repos()
            for r in repos:
                if r.local_path:
                    abs_p = os.path.realpath(r.local_path)
                    known_projects_map[abs_p] = r
        except Exception as e:
            logger.error(f"[ProjectSync] DB Scan failed: {e}")
            return

        known_paths = set(known_projects_map.keys())

        # 2. Check filesystem existence
        fs_paths = {p for p in known_paths if os.path.isdir(p)}

        # A. Restored Projects (In DB as DISCONNECTED, but now in FS)
        for p in known_paths & fs_paths:
            repo = known_projects_map[p]
            if repo.sync_status == "DISCONNECTED":
                logger.info(f"[ProjectSync] Restoring disconnected project: {p}")
                try:
                    async with session_scope() as session:
                        r = await session.get(Repository, repo.id)
                        if r:
                            r.sync_status = "SYNCED" if r.project_id else "PENDING_CREATION"
                            session.add(r)
                            repo.sync_status = r.sync_status
                except Exception as e:
                    logger.error(f"[ProjectSync] Failed to restore project {p}: {e}")

        # B. Retry Pending Cloud Sync for Syncing Projects
        for p in fs_paths:
            repo = known_projects_map[p]
            if repo.sync_status == "PENDING_CREATION":
                logger.info(f"[ProjectSync] Retrying cloud sync for: {p}")
                try:
                    from app.core.project.sync_tasks import sync_project_to_cloud_task

                    sync_project_to_cloud_task.delay(repo.id)
                except Exception as e:
                    logger.error(f"[ProjectSync] Failed to queue retry: {e}")

        # C. Restart watching for imported projects (SYNCED or PENDING_CREATION)
        imported_statuses = {"SYNCED", "PENDING_CREATION"}
        for p in fs_paths:
            repo = known_projects_map[p]
            if repo.sync_status in imported_statuses:
                logger.info(f"[ProjectSync] Restarting watcher for imported project: {p}")
                try:
                    from app.domain.codebase.indexing.manager import indexing_manager

                    if p not in indexing_manager._watchers:
                        await indexing_manager.start_watching(p, repo.id)

                    # Trigger background indexing if incomplete
                    if repo.indexing_status in ("pending", "failed") or not repo.last_indexed_at:
                        logger.info(f"[ProjectSync] Project {repo.name} indexing is incomplete, triggering background indexing")
                        asyncio.create_task(indexing_manager.run_indexing_background(repo.id))
                except Exception as e:
                    logger.error(f"[ProjectSync] Failed to restart watcher for {p}: {e}")

        # D. Deleted Projects (In DB, Not in FS)
        abs_root = os.path.realpath(root_path)
        missing_paths = []
        for p in known_paths:
            if p.startswith(abs_root) and p not in fs_paths:
                repo = known_projects_map[p]
                if repo.sync_status in imported_statuses:
                    missing_paths.append(p)

        for p in missing_paths:
            repo = known_projects_map[p]
            logger.info(f"[ProjectSync] Found offline deletion: {p}")
            await self.handle_project_deleted(p)

        logger.info(
            f"[ProjectSync] Reconciliation Complete. "
            f"Active: {len(fs_paths)}, "
            f"Missing: {len(missing_paths)}"
        )


# Global Instance
project_sync_service = ProjectSyncService()
