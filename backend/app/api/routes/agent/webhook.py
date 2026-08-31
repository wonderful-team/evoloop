import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.schemas.agent import WebhookRequest, WebhookResponse
from app.constants import DEFAULT_PROJECT_ID
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.agent import run_agent_background
from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
from app.core.evocloud import evocloud_manager
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.domain.integration.adapters import EventAdapter

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest, bg_tasks: BackgroundTasks):
    messages = EventAdapter.adapt(req.source, req.event_type, req.payload.model_dump())
    if not messages:
        raise HTTPException(status_code=400, detail="Could not adapt event")

    tid = req.thread_id or f"{req.source}-{req.payload.get('id', 'gen')}"
    ctx = EvoContext(thread_id=tid)
    ContextManager.set(ctx)

    if req.event_type == "project_switched":
        new_project = req.payload.get("new_project", {})
        new_path = new_project.get("path")
        if new_path:
            evocloud_manager.invalidate_projects_cache()
            logger.info("[Webhook] Project cache invalidated due to project_switched event")
            thread_context_store.set_working_directory(tid, new_path)
            repo_name = os.path.basename(new_path)
            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return WebhookResponse(status="switched", thread_id=tid)

    result = await dispatch_agent_run(
        thread_id=tid,
        message_content=messages[0].content if messages else "No content",
        project_id=DEFAULT_PROJECT_ID,
        metadata={"goal_prefix": f"[{req.source.capitalize()} Event] "},
    )

    if result.status == DispatchStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, tid, result.inputs)

    return WebhookResponse(status="accepted", thread_id=tid)
