import asyncio
import logging
import os

from sqlalchemy import select

from app.core.evocloud import evocloud_manager
from app.core.file import is_ignored_path
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

    Project Import Flow:
    1. File system detection -> Create Repository with sync_status="DETECTED"
    2. Publish NewProjectDetectedEvent -> Frontend shows notification
    3. User clicks "Import" -> import_project() updates status, starts indexing
    4. User clicks "Ignore" -> ignore_project() marks as ignored
    """

    def __init__(self):
        self._indexing_service = IndexingService()

    async def sync_cloud_project(self) -> None:
        """
        Sync the active project to local workspace on app start.

        Local-first strategy:
        1. Scan local WORKSPACE_ROOT for projects (via .evoloop/project.json).
        2. If there is a persisted active project_id, prefer that.
        3. Otherwise use the cloud's current project_id only as a hint.
        4. If the hinted project does not exist locally, do not auto-switch;
           log a clear message and wait for user action.
        5. Never use the cloud's external_path directly as the local path.
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
                    for pid in local_index.keys():
                        try:
                            await evocloud_manager.api.update_project(project_id=pid, source=device_key)
                            logger.info(f"[ProjectSync] Aligned project {pid} source to {device_key} in cloud")
                        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as ex:
                            logger.warning(f"[ProjectSync] Failed to update project {pid} source to {device_key}: {ex}")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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
            await indexing_manager.start_watching(local_path, repo.id)

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ProjectSync] Error syncing cloud project: {e}", exc_info=True)

    async def handle_project_created(self, path: str):
        """
        Handle creation of a new local project directory.

        Smart Cloud-Local Sync Strategy:
        1. Check if project exists in Cloud (by name or path)
        2. If Cloud exists + Local exists -> Auto-link, start indexing (SYNCED)
        3. If Cloud not exists + Local exists -> Create as DETECTED, notify user
        4. Publish NewProjectDetectedEvent only for case 3

        Indexing is NOT started until user confirms import (case 3).
        """
        repo_name = os.path.basename(path)
        abs_path = os.path.abspath(path)
        logger.info(f"[ProjectSync] Detected new project at: {path}")

        # Check if should auto-ignore (system directories, hidden files, etc.)
        if is_ignored_path(path):
            logger.info(f"[ProjectSync] Auto-ignoring system directory or hidden path: {path}")
            return

        # Check for existing record
        existing = await self._indexing_service.get_repo_by_path(path)
        if existing:
            # If existing is IGNORED, respect that choice and skip
            if existing.sync_status == "IGNORED":
                logger.info(f"[ProjectSync] Project {path} is already marked as IGNORED. Skipping.")
                # Ensure it's in the cache
                await project_cache.add_ignored_path(abs_path)
                return
            logger.info(f"[ProjectSync] Project already exists: {path}")
            return

        # Recovery: check if .evoloop/project.json exists (directory was moved while offline)
        # project.json travels with the directory and retains the original project_id
        project_json = read_project_json(abs_path)
        if project_json and project_json.get("project_id") and project_json["project_id"] > 0:
            recovered_project_id = int(project_json["project_id"])
            logger.info(
                f"[ProjectSync] Found .evoloop/project.json with project_id={recovered_project_id}. "
                f"Recovering cloud link for moved directory: {path}"
            )
            try:
                async with session_scope() as session:
                    # Check if a Repository with this project_id already exists (active)
                    from sqlalchemy import select as sa_select
                    stmt = sa_select(Repository).where(
                        Repository.project_id == recovered_project_id,
                        Repository.sync_status.notin_(["IGNORED", "DISCONNECTED"]),
                    )
                    result = await session.execute(stmt)
                    existing_repo = result.scalars().first()

                    if existing_repo:
                        # Update the existing repo's path to the new location
                        existing_repo.local_path = path
                        existing_repo.relative_path = repo_name
                        existing_repo.sync_status = "SYNCED"
                        await session.commit()
                        await session.refresh(existing_repo)
                        logger.info(
                            f"[ProjectSync] Updated existing Repository {existing_repo.id} "
                            f"to new path {path} (project_id={recovered_project_id})"
                        )
                        # Update project.json with current repo_id
                        write_project_json(abs_path, {
                            "project_id": recovered_project_id,
                            "repo_id": existing_repo.id,
                        })
                        # Sync cloud external_path to the new location
                        await self._update_cloud_project_path(recovered_project_id, abs_path)
                        # Trigger re-indexing at new path
                        await self._trigger_auto_indexing(existing_repo, path)
                        return
                    else:
                        # No existing active repo for this project_id — create new one
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
                            f"project_id={recovered_project_id} at moved path {path}"
                        )
                        write_project_json(abs_path, {
                            "project_id": recovered_project_id,
                            "repo_id": repo.id,
                        })
                        await self._update_cloud_project_path(recovered_project_id, abs_path)
                        await self._trigger_auto_indexing(repo, path)
                        return
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(
                    f"[ProjectSync] Failed to recover project from project.json: {e}. "
                    f"Falling through to normal detection flow."
                )

        # Check if there's an ignored project with the same name (recreated project)
        # This handles the case where user deleted and recreated the project folder
        if await self._is_repo_name_ignored_in_db(repo_name):
            logger.info(f"[ProjectSync] Project '{repo_name}' was previously ignored. Creating as IGNORED.")
            await self._create_ignored_project(path)
            return

        # Step 1: Scan Cloud projects to find potential match
        cloud_project = await self._find_matching_cloud_project(repo_name, abs_path)

        try:
            # Create Repository with DETECTED status (awaiting user confirmation)
            async with session_scope() as session:
                if cloud_project:
                    # Case 2: Cloud exists + Local exists -> Auto-link
                    raw_pid = cloud_project.get("project_id")
                    resolved = raw_pid if raw_pid is not None else cloud_project.get("id")
                    cloud_project_id = int(resolved) if resolved is not None else None
                    logger.info(f"[ProjectSync] Auto-linking local project '{repo_name}' to Cloud Project ID: {cloud_project_id}")

                    repo = Repository(
                        name=repo_name,
                        url="local",
                        local_path=path,
                        relative_path=repo_name,
                        sync_status="SYNCED",  # Directly synced
                        indexing_status="pending",  # Will be indexed after auto-link
                        detected_at=utcnow(),
                        imported_at=utcnow(),
                        project_id=cloud_project_id,
                    )
                    session.add(repo)
                    await session.commit()
                    await session.refresh(repo)

                    logger.info(f"[ProjectSync] Project '{repo_name}' auto-linked and SYNCED (ID: {repo.id})")

                    # Persist project_id and repo_id into local .evoloop/project.json
                    write_project_json(abs_path, {"project_id": cloud_project_id, "repo_id": repo.id})

                    # Sync device source to cloud so mobile can find this project
                    try:
                        from app.core.identity import identity_service
                        device_key = await identity_service.store.get_device_key()
                        if device_key:
                            await evocloud_manager.api.update_project(
                                project_id=cloud_project_id,
                                source=device_key,
                            )
                            logger.info(
                                f"[ProjectSync] Updated project {cloud_project_id} "
                                f"source to device key {device_key}"
                            )
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                        logger.warning(
                            f"[ProjectSync] Failed to update project "
                            f"{cloud_project_id} source: {e}"
                        )

                    # Auto-trigger indexing (no user confirmation needed)
                    await self._trigger_auto_indexing(repo, path)

                else:
                    # Case 3: Cloud not exists + Local exists -> Wait for user import
                    repo = Repository(
                        name=repo_name,
                        url="local",
                        local_path=path,
                        relative_path=repo_name,
                        sync_status="DETECTED",
                        indexing_status="not_needed",  # Not indexed until user imports
                        detected_at=utcnow(),
                        project_id=None,
                    )
                    session.add(repo)
                    await session.commit()
                    await session.refresh(repo)

                    logger.info(f"[ProjectSync] Project '{repo_name}' created with status DETECTED (ID: {repo.id})")

                    # Publish NewProjectDetectedEvent for frontend notification
                    from app.core.project.event.publishers import (
                        publish_new_project_detected,
                    )

                    await publish_new_project_detected(
                        repo_id=repo.id,
                        path=path,
                        name=repo_name,
                        detected_at=repo.detected_at
                    )

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Failed to create repository record: {e}")

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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ProjectSync] Failed to update cloud path for project {project_id}: {e}")

    async def _find_matching_cloud_project(self, repo_name: str, local_path: str) -> dict | None:
        """
        Find matching cloud project by local path or explicit project_id hint.

        We deliberately do NOT match by project name alone, because two
        different projects can share the same basename across devices.
        The only safe identifiers are:
        - exact local path match (cloud external_path == local_path)
        - an explicit project_id provided by the caller (handled separately)
        """
        try:
            cloud_projects = await evocloud_manager.scan_projects()
            abs_local_path = os.path.abspath(local_path)

            for project in cloud_projects:
                cloud_path = project.get("path", "")

                # Match by exact path only
                if cloud_path and os.path.abspath(cloud_path) == abs_local_path:
                    logger.info(f"[ProjectSync] Matched cloud project by path: {abs_local_path}")
                    return project

            logger.info(f"[ProjectSync] No cloud project matched local path: {abs_local_path}")
            return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ProjectSync] Failed to scan cloud projects: {e}. Treating as new project.")
            return None

    async def _trigger_auto_indexing(self, repo: Repository, path: str):
        """
        Auto-trigger indexing for auto-linked projects.
        Called when cloud project exists locally.
        """
        try:
            from app.core.project.event.publishers import publish_project_created

            # Publish ProjectCreatedEvent to trigger indexing
            await publish_project_created(
                path=path,
                repo_id=repo.id,
                project_id=repo.project_id,
                project_name=repo.name
            )
            logger.info(f"[ProjectSync] Auto-triggered indexing for '{repo.name}' (Repo ID: {repo.id})")

            # Start watching
            from app.domain.codebase.indexing.manager import indexing_manager
            await indexing_manager.start_watching(path, repo.id)

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Failed to auto-trigger indexing for '{repo.name}': {e}")

    async def import_project(self, repo_id: int) -> Repository:
        """
        Import a detected project (user confirmed).

        This method:
        1. Updates Repository status to PENDING_CREATION
        2. Syncs project to Cloud synchronously (blocks until cloud project is created)
        3. Publishes ProjectCreatedEvent to trigger indexing

        Args:
            repo_id: The Repository ID to import

        Returns:
            The updated Repository object

        Raises:
            ValueError: If repository not found or already imported
        """
        async with session_scope() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status not in ["DETECTED", "IGNORED"]:
                logger.warning(f"[ProjectSync] Project {repo_id} already imported (status: {repo.sync_status})")
                return repo

            # Update status
            repo.sync_status = "PENDING_CREATION"
            repo.indexing_status = "pending"
            repo.imported_at = utcnow()

            logger.info(f"[ProjectSync] Project '{repo.name}' imported by user (ID: {repo_id})")

            # Sync to Cloud synchronously
            cloud_project_id = None
            try:
                res = await evocloud_manager.api.create_project(
                    name=repo.name,
                    description=f"Imported from {repo.local_path}",
                    path=repo.local_path,
                )
                if res.get("code") == 0:
                    new_pid = int(res["data"]["project_id"])
                    repo.project_id = new_pid
                    repo.sync_status = "SYNCED"
                    cloud_project_id = new_pid
                    evocloud_manager.invalidate_projects_cache()
                    logger.info(f"[ProjectSync] Project '{repo.name}' synced to cloud (ID: {new_pid})")
                else:
                    logger.warning(f"[ProjectSync] Cloud create failed: {res.get('message')}")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[ProjectSync] Cloud sync failed: {e}")

        # Persist project_id and repo_id into local .evoloop/project.json
        if cloud_project_id and repo.local_path:
            write_project_json(repo.local_path, {"project_id": cloud_project_id, "repo_id": repo.id})

        # Publish ProjectCreatedEvent to trigger indexing
        try:
            from app.core.project.event.publishers import publish_project_created

            await publish_project_created(
                path=repo.local_path,
                repo_id=repo.id,
                project_id=repo.project_id,
                project_name=repo.name
            )
            logger.info(f"[ProjectSync] Published ProjectCreatedEvent for {repo.name}")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectCreatedEvent: {e}")

        return repo

    async def ignore_project(self, repo_id: int):
        """
        Ignore a detected project (user chose not to import).

        Marks the repository as IGNORED. Can be re-imported later via unignore_project.
        Also updates the ignored projects cache to exclude from tree views.
        """
        async with session_scope() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status != "DETECTED":
                logger.warning(f"[ProjectSync] Cannot ignore project with status: {repo.sync_status}")
                return

            repo.sync_status = "IGNORED"
            repo.indexing_status = "not_needed"  # Ignored projects don't need indexing

            logger.info(f"[ProjectSync] Project '{repo.name}' ignored by user (ID: {repo_id})")

            # Update cache to exclude from tree views
            if repo.local_path:
                await project_cache.add_ignored_path(repo.local_path)

    async def unignore_project(self, repo_id: int) -> Repository:
        """
        Restore an ignored project to detected status (can be imported).
        Also removes from the ignored projects cache.
        """
        async with session_scope() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            if repo.sync_status != "IGNORED":
                logger.warning(f"[ProjectSync] Project {repo_id} is not ignored (status: {repo.sync_status})")
                return repo

            repo.sync_status = "DETECTED"
            repo.indexing_status = "not_needed"  # Reset to not needed until imported

            logger.info(f"[ProjectSync] Project '{repo.name}' restored to DETECTED (ID: {repo_id})")

            # Update cache to re-include in tree views
            if repo.local_path:
                await project_cache.remove_ignored_path(repo.local_path)

            return repo

    async def get_detected_projects(self, member_id: int | None = None) -> list[Repository]:
        """Get all projects with DETECTED status (awaiting user confirmation)."""
        async with session_scope() as session:
            stmt = select(Repository).where(
                Repository.sync_status == "DETECTED"
            )
            if member_id is not None:
                stmt = stmt.where(Repository.member_id == member_id)
            stmt = stmt.order_by(Repository.detected_at.desc())

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_ignored_projects(self, member_id: int | None = None) -> list[Repository]:
        """Get all projects with IGNORED status."""
        async with session_scope() as session:
            stmt = select(Repository).where(
                Repository.sync_status == "IGNORED"
            )
            if member_id is not None:
                stmt = stmt.where(Repository.member_id == member_id)
            stmt = stmt.order_by(Repository.detected_at.desc())

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def handle_project_deleted(self, path: str):
        """
        Handle deletion of a local project directory.
        Includes an idempotency guard to prevent infinite event loops.
        """
        repo_name = os.path.basename(path)

        # 1. Fetch ALL records for this path (handling duplicates)
        try:
            async with session_scope() as session:
                stmt = select(Repository).where(Repository.local_path == path)
                result = await session.execute(stmt)
                all_repos = result.scalars().all()

                if not all_repos:
                    logger.debug(f"[ProjectSync] No repository records found for path: {path}")
                    return

                # 2. Filter records that are NOT yet marked as DISCONNECTED
                to_disconnect = [r for r in all_repos if r.sync_status != "DISCONNECTED"]

                # 3. Guard: If all are already DISCONNECTED, stop here to prevent infinite event loop
                if not to_disconnect:
                    logger.debug(f"[ProjectSync] Project {repo_name} already marked as DISCONNECTED. Skipping.")
                    return

                # 4. Perform batch update in a single transaction
                # Fetch fresh objects in the current session to update
                for r in to_disconnect:
                    db_repo = await session.get(Repository, r.id)
                    if db_repo:
                        db_repo.sync_status = "DISCONNECTED"


                # Metadata for event (use the first updated record)
                repo_id = to_disconnect[0].id
                project_id = to_disconnect[0].project_id

                logger.info(f"[ProjectSync] Project {repo_name} marked as DISCONNECTED ({len(to_disconnect)} records updated).")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Error updating disconnect status for {path}: {e}")
            return

        # 5. Publish ProjectDeletedEvent (only once after successful DB update)
        # IndexingManager will subscribe and stop watching
        try:
            from app.core.project.event.publishers import publish_project_deleted

            await publish_project_deleted(
                path=path,
                repo_id=repo_id or 0,
                project_id=project_id
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Failed to publish ProjectDeletedEvent for {path}: {e}")

    async def handle_project_moved(self, src_path: str, dest_path: str):
        """
        Handle move/rename of a local project.
        """
        new_name = os.path.basename(dest_path)
        logger.info(f"[ProjectSync] Detected Move: {src_path} -> {dest_path}")

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
                # Invalidate cache to reflect updated project info
                evocloud_manager.invalidate_projects_cache()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[ProjectSync] Cloud Update Failed: {e}")

        # 5. Update Local Record
        async with self._indexing_service.session_factory() as session:
            r = await session.get(type(repo), repo.id)
            if r:
                r.local_path = dest_path
                r.relative_path = new_name
                r.name = new_name
                # If it was disconnected, moving it might reconnect it?
                if r.sync_status == "DISCONNECTED":
                    r.sync_status = "SYNCED"
                session.add(r)

        # Note: .evoloop/project.json moves with the directory, so project_id is preserved.
        # 6. Start New Watch
        await indexing_manager.start_watching(dest_path, repo.id)

    async def _resolve_existing_project_id(self, path: str) -> int | None:
        """Try to resolve Project ID from Context/Settings/Cache."""
        try:
            projects = await evocloud_manager.scan_projects()
            abs_path = os.path.abspath(path)
            for p in projects:
                if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                    return p.get("id")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
        return None

    async def reconcile_projects(self, root_path: str, force: bool = False):
        """
        Reconcile local filesystem projects with system state (DB/Cloud).
        Handles creation/deletion that occurred while service was offline.

        Modified: Only starts indexing for already-imported projects.
        Newly detected projects are created with DETECTED status (if discovery enabled or force=True).
        Respects user's ignored project choices.
        """
        if not root_path or not os.path.exists(root_path):
            logger.warning(f"[ProjectSync] Root path {root_path} invalid. Skipping reconciliation.")
            return

        # Check if project discovery is enabled
        from app.infrastructure.config.service import SystemConfigService
        discovery_config = SystemConfigService.get_value("PROJECT_DISCOVERY_ENABLED")
        is_discovery_enabled = force or discovery_config is None or discovery_config.lower() in ("true", "1", "yes", "on")

        if not is_discovery_enabled:
            logger.info("[ProjectSync] Project discovery is disabled. Skipping new project detection.")

        if force:
            logger.info("[ProjectSync] Forced reconciliation triggered. Ignoring discovery config.")

        logger.info(f"[ProjectSync] Starting Reconciliation on {root_path}...")

        # 1. Scan Filesystem (Direct subdirectories only using unified traverser)
        fs_projects = set()
        from app.core.file import FileTraverser
        try:
            for entry in FileTraverser.list_entries(root_path):
                if entry.is_dir():
                    # Use absolute path for consistency
                    fs_projects.add(os.path.abspath(entry.path))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] FS Scan failed: {e}")
            return

        # 2. Get Known Projects (Local DB)
        known_projects_map = {}
        ignored_paths = set()  # Track ignored project paths
        try:
            repos = await self._indexing_service.get_all_repos()
            for r in repos:
                if r.local_path:
                    abs_p = os.path.abspath(r.local_path)
                    known_projects_map[abs_p] = r
                    # Track ignored projects to skip them during reconciliation
                    if r.sync_status == "IGNORED":
                        ignored_paths.add(abs_p)
                        logger.debug(f"[ProjectSync] Tracked ignored project: {abs_p}")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] DB Scan failed: {e}")
            return

        # 3. Detect Changes
        known_paths = set(known_projects_map.keys())
        fs_paths = {os.path.abspath(p) for p in fs_projects}

        # A. New Projects (In FS, Not in DB)
        # Create as DETECTED only if discovery is enabled, don't start indexing
        # But skip if this path was previously ignored
        new_paths = fs_paths - known_paths
        if is_discovery_enabled:
            for p in new_paths:
                # Check if this path matches an ignored project (by name match)
                # This handles the case where user deleted and re-created a project
                if self._matches_previously_ignored_project(p, ignored_paths):
                    logger.info(f"[ProjectSync] Skipping previously ignored project: {p}")
                    # Create as IGNORED to maintain user choice
                    await self._create_ignored_project(p)
                    continue

                logger.info(f"[ProjectSync] Found offline creation: {p}")
                await self.handle_project_created(p)
        else:
            # Discovery disabled - only log how many projects were found but not created
            if new_paths:
                logger.info(f"[ProjectSync] Found {len(new_paths)} new projects but discovery is disabled. Skipping.")

        # B. Restored Projects (In DB as DISCONNECTED, but now in FS)
        for p in known_paths & fs_paths:
            repo = known_projects_map[p]
            if repo.sync_status == "DISCONNECTED":
                logger.info(f"[ProjectSync] Restoring disconnected project: {p}")
                try:
                    async with session_scope() as session:
                        r = await session.get(Repository, repo.id)
                        if r:
                            # If it has project_id, it was likely SYNCED.
                            # If not, it was DETECTED or PENDING_CREATION.
                            if r.project_id:
                                r.sync_status = "SYNCED"
                            else:
                                r.sync_status = "DETECTED"
                            session.add(r)
                            # Update map for subsequent steps
                            repo.sync_status = r.sync_status
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"[ProjectSync] Failed to restore project {p}: {e}")

        # C. Retry Pending Cloud Sync for Imported Projects
        for p in known_paths:
            if p in fs_paths:
                repo = known_projects_map[p]
                # Retry cloud sync for imported projects that failed
                if repo.sync_status == "PENDING_CREATION":
                    logger.info(f"[ProjectSync] Retrying cloud sync for: {p}")
                    try:
                        from app.core.project.sync_tasks import (
                            sync_project_to_cloud_task,
                        )
                        sync_project_to_cloud_task.delay(repo.id)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                        logger.error(f"[ProjectSync] Failed to queue retry: {e}")

        # C. Restart watching for imported projects (SYNCED or PENDING_CREATION)
        # Explicitly exclude IGNORED projects
        imported_statuses = {"SYNCED", "PENDING_CREATION"}
        imported_paths = {
            p for p in known_paths
            if known_projects_map[p].sync_status in imported_statuses
            and known_projects_map[p].sync_status != "IGNORED"
        }

        for p in imported_paths & fs_paths:
            repo = known_projects_map[p]
            logger.info(f"[ProjectSync] Restarting watcher for imported project: {p}")
            try:
                from app.domain.codebase.indexing.manager import indexing_manager

                # Check if already watching
                if p not in indexing_manager._watchers:
                    await indexing_manager.start_watching(p, repo.id)

                # Check if indexing is incomplete and trigger background indexing
                # This handles cases where previous indexing failed or was interrupted
                if repo.indexing_status in ("pending", "failed") or not repo.last_indexed_at:
                    logger.info(f"[ProjectSync] Project {repo.name} indexing status is {repo.indexing_status}, triggering background indexing")
                    # Fire and forget - don't await background indexing
                    asyncio.create_task(indexing_manager.run_indexing_background(repo.id))
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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

    def _matches_previously_ignored_project(self, path: str, ignored_paths: set) -> bool:
        """
        Check if a path matches any previously ignored project.
        Matches by exact path or by directory name.

        Args:
            path: The path to check
            ignored_paths: Set of ignored project paths

        Returns:
            True if the path should be treated as ignored
        """
        abs_path = os.path.abspath(path)

        # Check exact path match
        if abs_path in ignored_paths:
            return True

        # Check if the directory name matches any ignored project name
        # This handles the case where user deleted and recreated the project
        dir_name = os.path.basename(abs_path)
        for ignored_path in ignored_paths:
            ignored_name = os.path.basename(ignored_path)
            if dir_name == ignored_name:
                logger.info(f"[ProjectSync] Path {abs_path} matches ignored project name: {ignored_name}")
                return True

        return False

    async def _is_repo_name_ignored_in_db(self, repo_name: str) -> bool:
        """
        Check if a project with this name was previously ignored.
        This handles the case where user deleted and recreated the project.

        Args:
            repo_name: The name of the repository (directory name)

        Returns:
            True if a project with this name was previously ignored
        """
        try:
            async with session_scope() as session:
                stmt = select(Repository).where(
                    Repository.name == repo_name,
                    Repository.sync_status == "IGNORED"
                )
                result = await session.execute(stmt)
                ignored_repo = result.scalar_one_or_none()
                return ignored_repo is not None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[ProjectSync] Error checking previously ignored status: {e}")
            return False

    async def _create_ignored_project(self, path: str):
        """
        Create a repository record with IGNORED status.
        Used when a previously ignored project is detected again.
        """
        repo_name = os.path.basename(path)
        abs_path = os.path.abspath(path)

        try:
            async with session_scope() as session:
                repo = Repository(
                    name=repo_name,
                    url="local",
                    local_path=path,
                    sync_status="IGNORED",  # Maintain ignored status
                    indexing_status="not_needed",  # Ignored projects are not indexed
                    detected_at=utcnow(),
                    project_id=None,
                )
                session.add(repo)
                await session.commit()
                await session.refresh(repo)

            logger.info(f"[ProjectSync] Created IGNORED project record for: {path}")

            # Update cache
            await project_cache.add_ignored_path(abs_path)

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectSync] Failed to create ignored project record: {e}")


# Global Instance
project_sync_service = ProjectSyncService()
