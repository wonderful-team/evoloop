import logging
import os
import asyncio
from typing import Optional

from app.logging import logger
from app.infrastructure.external.imagicbox import imagicbox_client
from app.domain.codebase.indexing.service import IndexingService
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.service import project_context_manager


class ProjectSyncService:
    """
    Service responsible for synchronizing local project state with the Cloud (ImagicBox).
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
                logger.info(f"[ProjectSync] Created local record (Pending Cloud Sync)")

        except Exception as e:
            logger.error(f"[ProjectSync] Failed to create local repository record: {e}")
            return

        # 3. Cloud Sync (If not already linked)
        if not repo.project_id:
            logger.info(f"[ProjectSync] Attempting to create project '{repo_name}' in Cloud...")
            try:
                res = await imagicbox_client.create_project(
                    name=repo_name,
                    description=f"Imported from {path}",
                    path=path
                )

                if res.get("code") == 0:
                    new_pid = res["data"]["id"]
                    logger.info(f"[ProjectSync] Cloud Creation Success! Project ID: {new_pid}")

                    # Update Local Record
                    async with self._indexing_service.session_factory() as session:
                        r = await session.get(type(repo), repo.id)
                        if r:
                            r.project_id = new_pid
                            r.sync_status = "SYNCED"
                            session.add(r)
                            await session.commit()
                            # Update local var for next steps
                            repo.project_id = new_pid
                else:
                    logger.error(f"[ProjectSync] Cloud Creation Failed: {res.get('message')}")
                    # We remain in PENDING state. 
                    # TODO: Queue for retry? For now, we just leave it. 
                    # User might retry seamlessly or background job can pick it up.
            except Exception as e:
                logger.error(f"[ProjectSync] Cloud API Error: {e}")
                # Remain PENDING.

        # 4. Start Indexing
        # We start watching and indexing regardless of Cloud status.
        try:
            await indexing_manager.start_watching(path, repo.id)
            # Use repo-based indexing trigger which handles missing project_id gracefully (by just indexing local files)
            await indexing_manager.trigger_full_index_for_repo(repo.id)
        except Exception as e:
            logger.error(f"[ProjectSync] Failed to start indexing: {e}")

    async def handle_project_deleted(self, path: str):
        """
        Handle deletion of a local project directory.
        """
        repo_name = os.path.basename(path)

        # 1. Stop Watching
        try:
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
            await indexing_manager.stop_watching(src_path)

            # 3. Update Cloud (Best Effort)
            if repo.project_id:
                try:
                    await imagicbox_client.update_project(
                        project_id=repo.project_id,
                        name=new_name,
                        path=dest_path
                    )
                    logger.info(f"[ProjectSync] Cloud Project Updated.")
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

    async def _resolve_existing_project_id(self, path: str) -> Optional[int]:
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


# Global Instance
project_sync_service = ProjectSyncService()
