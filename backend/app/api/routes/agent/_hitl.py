import logging
import time

from fastapi import APIRouter, BackgroundTasks

from app.api.schemas.agent import CancelHITLRequest, CancelHITLResponse
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine.graph_runner import resume_graph_background
from app.core.engine.message.native_classes import ToolMessage
from app.core.monitoring.activity import activity_monitor

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/hitl/cancel")
async def cancel_hitl_request(req: CancelHITLRequest, bg_tasks: BackgroundTasks):
    from app.core.hitl.orchestrator import HITLOrchestrator

    active_model = req.model
    if not active_model:
        loaded_ctx = await ContextManager.load(req.thread_id)
        if loaded_ctx:
            active_model = loaded_ctx.active_model

    pending_tool = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)

    await activity_monitor.clear_human_request(req.thread_id)

    if not pending_tool:
        return CancelHITLResponse(status="cancelled", thread_id=req.thread_id, request_id=None)

    logger.info(f"Auto-cancelling tool call {pending_tool['name']} on cancel")
    cancellation_result = await HITLOrchestrator.handle_cancel(req.thread_id, pending_tool)

    tool_msg = ToolMessage(tool_call_id=pending_tool["id"], content=cancellation_result)
    inputs = {"messages": [tool_msg]}

    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": active_model,
            "run_id": f"cancel-{req.thread_id}-{int(time.time())}",
        },
        "metadata": {"project_id": req.project_id},
    }

    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(
            resume_graph_background, req.thread_id, inputs, config,
            run_label="Resuming after cancellation...",
        )
    else:
        from app.core.engine.message.converter import EvoMessageConverter

        serialized_inputs = inputs.copy() if inputs else {}
        if "messages" in serialized_inputs:
            serialized_inputs["messages"] = EvoMessageConverter.repair(serialized_inputs["messages"])

        from app.infrastructure.queue.factory import get_scheduler

        get_scheduler().send_task(
            "engine_resume_graph_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming after cancellation...", False),
        )

    return CancelHITLResponse(
        status="cancelled",
        thread_id=req.thread_id,
        request_id=pending_tool["id"] if pending_tool else None,
    )
