import logging

from app.core.evocloud import evocloud_manager
from app.domain.codebase.constants import REPO_SYNC_STATUS_SYNCED
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.queue.factory import shared_task
from app.models.codebase import Repository
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@shared_task(
    name="sync_project_to_cloud",
    bind=True,
    autoretry_for=(RuntimeError, OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,  # 5 minutes max backoff
    max_retries=5,
)
async def sync_project_to_cloud_task(_self, repo_id: int):
    """
    Background task to sync a local project to EvoCloud.
    Retries automatically on failure.
    """
    logger.info(f"[SyncTask] Starting Cloud Sync for Repo ID: {repo_id}")

    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False)

    try:
        indexing_service = IndexingService()

        async with indexing_service.session_factory() as session:
            repo = await session.get(Repository, repo_id)
            if not repo:
                logger.error(f"[SyncTask] Repo {repo_id} not found.")
                return

            if repo.project_id:
                logger.info(
                    f"[SyncTask] Repo {repo_id} already synced (PID: {repo.project_id}). Skipping."
                )
                return

            try:
                logger.info(f"[SyncTask] Creating project '{repo.name}' in Cloud...")
                res = await evocloud_manager.api.create_project(
                    name=repo.name,
                    description=f"Imported from {repo.local_path}",
                    path=repo.local_path,
                )

                if res.get("code") == 0:
                    new_pid = res["data"]["project_id"]
                    logger.info(f"[SyncTask] Success! Project ID: {new_pid}")

                    repo.project_id = new_pid
                    repo.sync_status = REPO_SYNC_STATUS_SYNCED
                    session.add(repo)
                else:
                    raise RuntimeError(f"Cloud API Failed: {res.get('message')}")

            except Exception as e:
                logger.exception(f"[SyncTask] Sync Failed: {e}")
                raise e  # Trigger Retry
    finally:
        await flush_loop_bound_resources()


@shared_task(
    name="sync_cloud_projects",
    retries=1,
    retry_delay=30,
)
async def sync_cloud_projects_task() -> None:
    """Align local projects with EvoCloud in the background.

    Moved off the API startup critical path: the local workspace scan and the
    sequential cloud HTTP calls (project source alignment + current-project
    hint) previously blocked APP_STARTED for ~1.4s. Watchers and
    working-directory state stay in the API process (handled by
    ``reconcile_projects`` / ``ProjectSwitchedEvent``), so they are skipped here.
    """
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False)

    try:
        from app.core.project.sync_service import project_sync_service

        await project_sync_service.sync_cloud_project(start_watchers=False)
    finally:
        await flush_loop_bound_resources()
