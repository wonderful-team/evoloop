import logging
from datetime import datetime

from app.infrastructure.queue.celery import celery_app
from app.core.evocloud import evocloud_manager
from app.domain.codebase.indexing.service import IndexingService
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


@celery_app.task(
    name="sync_project_to_cloud",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,  # 5 minutes max backoff
    max_retries=5,
)
def sync_project_to_cloud_task(_self, repo_id: int):
    """
    Background task to sync a local project to EvoCloud.
    Retries automatically on failure.
    """
    logger.info(f"[SyncTask] Starting Cloud Sync for Repo ID: {repo_id}")

    # Need to run async code in sync Celery worker
    import asyncio

    async def _sync():
        indexing_service = IndexingService()

        async with indexing_service.session_factory() as session:
            repo = await session.get(type(await indexing_service.get_or_create_repo(".", "dummy")), repo_id)
            if not repo:
                logger.error(f"[SyncTask] Repo {repo_id} not found.")
                return

            if repo.project_id:
                logger.info(f"[SyncTask] Repo {repo_id} already synced (PID: {repo.project_id}). Skipping.")
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
                    repo.sync_status = "SYNCED"
                    session.add(repo)
                    await session.commit()
                else:
                    raise Exception(f"Cloud API Failed: {res.get('message')}")

            except Exception as e:
                logger.error(f"[SyncTask] Sync Failed: {e}")
                raise e  # Trigger Retry

    async def _run_with_flush():
        try:
            await _sync()
        finally:
            await flush_loop_bound_resources()

    # Run the async loop
    asyncio.run(_run_with_flush())


@celery_app.task(
    name="sync_tasks_to_evocloud",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def sync_tasks_to_evocloud_task(_self, analysis_id: str, task_ids: list[str]):
    """
    Background task to sync requirement tasks to EvoCloud.
    Called automatically after requirement analysis is confirmed.
    """
    import asyncio

    from app.domain.project.requirements.models import ProjectRequirementTask
    from app.infrastructure.database.sql.database import async_session_factory

    async def _sync():
        logger.info(f"[ReqSync] Starting sync for analysis {analysis_id}, {len(task_ids)} tasks")

        async with async_session_factory() as session:
            from sqlalchemy import select

            # Get all tasks to sync
            stmt = select(ProjectRequirementTask).where(
                ProjectRequirementTask.id.in_(task_ids)
            )
            result = await session.execute(stmt)
            tasks = result.scalars().all()

            if not tasks:
                logger.warning(f"[ReqSync] No tasks found for analysis {analysis_id}")
                return

            synced_count = 0
            failed_count = 0

            for task in tasks:
                try:
                    task_data = task.task_data

                    # Prepare EvoCloud payload
                    payload = {
                        "project_id": task.project_id,
                        "task_name": task_data.get("title", "Untitled"),
                        "task_desc": _format_task_description(task_data),
                        "priority": _map_priority(task_data.get("priority", "medium")),
                        "estimated_time": task_data.get("estimated_hours", 0),
                        "tags": task_data.get("tags", []),
                    }

                    # Call EvoCloud API
                    result = await evocloud_manager.api.create_task(payload)

                    if result.get("code") == 0:
                        task.evocloud_task_id = result["data"]["task_id"]
                        task.sync_status = "synced"
                        task.synced_at = datetime.now()
                        synced_count += 1
                        logger.info(f"[ReqSync] Task {task.id} synced: {task.evocloud_task_id}")
                    else:
                        task.sync_status = "failed"
                        task.sync_error = result.get("message", "Unknown error")
                        failed_count += 1
                        logger.error(f"[ReqSync] Task {task.id} failed: {task.sync_error}")

                except Exception as e:
                    task.sync_status = "failed"
                    task.sync_error = str(e)
                    failed_count += 1
                    logger.exception(f"[ReqSync] Task {task.id} exception: {e}")

            await session.commit()

    async def _run_with_flush():
        try:
            await _sync()
        finally:
            await flush_loop_bound_resources()

    asyncio.run(_run_with_flush())


def _map_priority(priority: str) -> int:
    """Map priority string to EvoCloud priority number."""
    mapping = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
    return mapping.get(priority.lower(), 3)


def _format_task_description(task_data: dict) -> str:
    """Format task data into description for EvoCloud."""
    lines = [task_data.get("description", "")]

    # Add requirement refs
    refs = task_data.get("requirement_refs", [])
    if refs:
        lines.append(f"\n\n**关联需求**: {', '.join(refs)}")

    # Add acceptance criteria
    criteria = task_data.get("acceptance_criteria", [])
    if criteria:
        lines.append("\n\n**验收标准**:")
        for c in criteria:
            lines.append(f"- {c}")

    return "\n".join(lines)
