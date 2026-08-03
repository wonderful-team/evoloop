from fastapi import APIRouter, BackgroundTasks

# External dependencies used by agent endpoints that tests patch directly on agent module
from app.infrastructure.database.resource_manager import db_resource_manager

# Re-exports for test compatibility
from ._chat import (
    ChatRequest,
    ResumeRequest,
    _check_thread_not_running,
    activity_monitor,
    chat_endpoint,
    resume_chat,
    retry_chat,
    run_agent_background,
    session_scope,
    stop_chat,
    thread_context_store,
)
from ._chat import router as chat_router
from ._hitl import cancel_hitl_request, resume_graph_background
from ._hitl import router as hitl_router
from ._webhook import EventAdapter, WebhookRequest, evocloud_manager, webhook_endpoint
from ._webhook import router as webhook_router


async def _prepare_and_dispatch(
    thread_id: str,
    project_id: int,
    bg_tasks: BackgroundTasks,
    message_content: str | None = None,
    attachments: list | None = None,
    command_id: str | None = None,
    checkpoint_id: str | None = None,
    is_retry: bool = False,
    model: str | None = None,
):
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=project_id,
        command_id=command_id,
        active_model=model,
    )
    ContextManager.set(ctx)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message_content,
        project_id=project_id,
        references=attachments,
        command_id=command_id,
        checkpoint_id=checkpoint_id,
        is_retry=is_retry,
        model=model,
        context=ctx,
    )

    if result.status == "failed":
        raise Exception(result.error)

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    return {
        "status": "queued",
        "thread_id": thread_id,
        "message_id": result.message_id,
    }


router = APIRouter()
router.include_router(chat_router)
router.include_router(hitl_router)
router.include_router(webhook_router)

__all__ = [
    "router",
    "chat_endpoint",
    "stop_chat",
    "retry_chat",
    "resume_chat",
    "ChatRequest",
    "ResumeRequest",
    "activity_monitor",
    "session_scope",
    "run_agent_background",
    "thread_context_store",
    "_check_thread_not_running",
    "webhook_endpoint",
    "WebhookRequest",
    "EventAdapter",
    "evocloud_manager",
    "cancel_hitl_request",
    "resume_graph_background",
    "db_resource_manager",
    "_prepare_and_dispatch",
]
