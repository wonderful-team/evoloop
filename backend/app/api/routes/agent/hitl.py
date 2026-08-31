import logging

from fastapi import APIRouter, BackgroundTasks

from app.api.schemas.agent import CancelHITLRequest, CancelHITLResponse
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import ToolMessage
from app.core.engine.resume_runner import resume_agent_background
from app.core.hitl.types import HITLDecision
from app.core.monitoring.activity import activity_monitor
from app.utils.id import unique_id

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/hitl/cancel")
async def cancel_hitl_request(req: CancelHITLRequest, bg_tasks: BackgroundTasks):
    from app.core.engine.session.manager import session_manager
    from app.core.hitl.orchestrator import HITLOrchestrator

    active_model = req.model
    if not active_model:
        loaded_ctx = await ContextManager.load(req.thread_id)
        if loaded_ctx:
            active_model = loaded_ctx.active_model

    pending_tool = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)

    # 会话模式（§4.5）：活 session → 注入取消事件，由 session 主循环经 resume 链路
    # 统一处理（关闭 DB 双轨 + persist 拒绝结果 + Agent 继续），避免与单发
    # resume_agent_background 双执行。
    session = session_manager.get(req.thread_id)
    if session is not None and session.lifecycle == "running":
        if pending_tool:
            logger.info(
                "[HitlCancel] Live session %s, cancelling pending tool %s",
                req.thread_id, pending_tool["name"],
            )
        else:
            # 无 DB 请求但 activity 可能残留 → 手动清理状态
            await activity_monitor.clear_human_request(req.thread_id)
        session.inject_resume(HITLDecision.CANCELLED.value, is_cancel=True)
        return CancelHITLResponse(
            status="cancelled",
            thread_id=req.thread_id,
            request_id=pending_tool["id"] if pending_tool else None,
        )

    # 单发（无活会话）路径
    if not pending_tool:
        await activity_monitor.clear_human_request(req.thread_id)
        return CancelHITLResponse(status="cancelled", thread_id=req.thread_id, request_id=None)

    logger.info(f"Auto-cancelling tool call {pending_tool['name']} on cancel")
    cancellation_result = await HITLOrchestrator.handle_cancel(req.thread_id, pending_tool)

    tool_msg = ToolMessage(tool_call_id=pending_tool["id"], content=cancellation_result)
    inputs = {"messages": [tool_msg]}

    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": active_model,
            "run_id": unique_id("cancel", req.thread_id),
        },
        "metadata": {"project_id": req.project_id},
    }

    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(
            resume_agent_background, req.thread_id, inputs, config,
            run_label="Resuming after cancellation...",
        )
    else:
        from app.core.engine.message.converter import EvoMessageConverter

        serialized_inputs = inputs.copy() if inputs else {}
        if "messages" in serialized_inputs:
            serialized_inputs["messages"] = EvoMessageConverter.repair(serialized_inputs["messages"])

        from app.infrastructure.queue.factory import get_scheduler

        get_scheduler().send_task(
            "engine_resume_agent_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming after cancellation...", False),
        )

    return CancelHITLResponse(
        status="cancelled",
        thread_id=req.thread_id,
        request_id=pending_tool["id"] if pending_tool else None,
    )
