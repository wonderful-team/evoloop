
import logging
from app.celery_app import celery_app
from app.infrastructure.external.evocloud import evocloud_client
from app.domain.codebase.indexing.service import IndexingService

logger = logging.getLogger(__name__)

@celery_app.task(
    name="sync_project_to_cloud",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300, # 5 minutes max backoff
    max_retries=5
)
def sync_project_to_cloud_task(self, repo_id: int):
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
                res = await evocloud_client.create_project(
                    name=repo.name,
                    description=f"Imported from {repo.local_path}",
                    path=repo.local_path
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
                raise e # Trigger Retry

    # Run the async loop
    asyncio.run(_sync())
