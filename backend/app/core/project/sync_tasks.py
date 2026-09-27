import logging
from datetime import datetime
from typing import Any

from app.core.evocloud import evocloud_manager
from app.core.evocloud.constants import SYNC_STATUS_FAILED, SYNC_STATUS_SYNCED
from app.core.project.constants import TASK_PRIORITY_MEDIUM
from app.domain.codebase.constants import REPO_SYNC_STATUS_SYNCED
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.queue.factory import shared_task
from app.models.codebase import Repository
from app.utils.async_utils import flush_loop_bound_resources
from app.utils.template import render_template

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
    name="sync_tasks_to_evocloud",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
async def sync_tasks_to_evocloud_task(
    _self, task_ids: list[str], analysis_id: str | None = None
):
    """
    Background task to sync requirement tasks to EvoCloud.
    Called automatically after requirement analysis is confirmed.
    """
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.project import ProjectTask

    await db_resource_manager.initialize(create_tables=False)

    logger.info(
        f"[ReqSync] Starting sync for analysis {analysis_id}, {len(task_ids)} tasks"
    )

    # Phase 1: load tasks with a short DB session
    task_snapshots: list[dict[str, Any]] = []
    try:
        async with session_scope() as session:
            stmt = select(ProjectTask).where(ProjectTask.id.in_(task_ids))
            result = await session.execute(stmt)
            task_snapshots = [
                {
                    "id": t.id,
                    "project_id": t.project_id,
                    "task_data": t.task_data,
                }
                for t in result.scalars().all()
            ]
    except Exception as e:
        logger.exception(f"[ReqSync] Failed to load tasks for analysis {analysis_id}: {e}")
        return

    if not task_snapshots:
        logger.warning(f"[ReqSync] No tasks found for analysis {analysis_id}")
        return

    # Phase 2: render description + call EvoCloud API **outside** DB session
    synced_count = 0
    failed_count = 0
    updates: list[dict[str, Any]] = []

    for snap in task_snapshots:
        task_id = snap["id"]
        task_data = snap["task_data"]
        try:
            payload = {
                "project_id": snap["project_id"],
                "task_name": task_data.get("title", "Untitled"),
                "task_desc": _format_task_description(task_data),
                "priority": _map_priority(task_data.get("priority", TASK_PRIORITY_MEDIUM)),
                "estimated_time": task_data.get("estimated_hours", 0),
                "tags": task_data.get("tags", []),
            }

            result = await evocloud_manager.api.create_task(payload)

            if result.get("code") == 0:
                updates.append({
                    "id": task_id,
                    "evocloud_task_id": result["data"]["task_id"],
                    "sync_status": SYNC_STATUS_SYNCED,
                    "sync_error": None,
                })
                synced_count += 1
                logger.info(f"[ReqSync] Task {task_id} synced: {result['data']['task_id']}")
            else:
                error_msg = result.get("message", "Unknown error")
                updates.append({
                    "id": task_id,
                    "evocloud_task_id": None,
                    "sync_status": SYNC_STATUS_FAILED,
                    "sync_error": error_msg,
                })
                failed_count += 1
                logger.error(f"[ReqSync] Task {task_id} failed: {error_msg}")
        except Exception as e:
            updates.append({
                "id": task_id,
                "evocloud_task_id": None,
                "sync_status": SYNC_STATUS_FAILED,
                "sync_error": str(e),
            })
            failed_count += 1
            logger.exception(f"[ReqSync] Task {task_id} exception: {e}")

    # Phase 3: persist sync results in another short DB session
    try:
        async with session_scope() as session:
            for upd in updates:
                task = await session.get(ProjectTask, upd["id"])
                if task is None:
                    continue
                task.evocloud_task_id = upd["evocloud_task_id"]
                task.sync_status = upd["sync_status"]
                task.sync_error = upd["sync_error"]
                if upd["sync_status"] == SYNC_STATUS_SYNCED:
                    task.synced_at = datetime.now()
    except Exception as e:
        logger.exception(f"[ReqSync] Failed to persist sync results for analysis {analysis_id}: {e}")
        return
    finally:
        await flush_loop_bound_resources()

    logger.info(
        f"[ReqSync] Sync complete for analysis {analysis_id}: "
        f"{synced_count} synced, {failed_count} failed"
    )


def _map_priority(priority: str) -> int:
    """Map priority string to EvoCloud priority number."""
    mapping = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
    return mapping.get(priority.lower(), 3)


def _format_task_description(task_data: dict) -> str:
    """Format task data into description for EvoCloud."""
    try:
        return render_template(
            "domain/project/project_management.prompt.j2",
            description=task_data.get("description", ""),
            references=task_data.get("requirement_refs", []),
            checklist=task_data.get("acceptance_criteria", []),
        )
    except Exception as e:
        logger.exception(f"Failed to render task description: {e}")
        return task_data.get("description", "Formatting error.")


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
