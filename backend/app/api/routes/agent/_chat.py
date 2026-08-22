import asyncio
import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserOptional,
    TokenDepOptional,
    verify_guest_access,
)
from app.api.schemas.agent import (
    ChatRequest,
    ResumeChatResponse,
    ResumeRequest,
    StopChatResponse,
)
from app.core.channel.input.web_input import web_input
from app.core.config import settings
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.graph_runner import resume_graph_background
from app.core.engine.message.native_classes import HumanMessage, ToolMessage
from app.core.execution.system_tools_formatter import SystemToolsFormatter
from app.core.monitoring.activity import activity_monitor
from app.core.routing.dispatch_handler import dispatch_user_message, route_lock_scope
from app.infrastructure.database import session_scope
from app.models import Message
from app.utils.id import gen_uuid

router = APIRouter()

logger = logging.getLogger(__name__)


async def _check_thread_not_running(thread_id: str) -> None:
    state = await activity_monitor.get_activity(thread_id)
    if state and state.status == "running":
        raise HTTPException(
            status_code=409,
            detail=f"Thread {thread_id} is currently processing. Please wait for it to complete.",
        )


@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(
    req: ChatRequest,
    _current_user: CurrentUserOptional,
    token: TokenDepOptional = None,
):
    if not req.thread_id:
        req.thread_id = gen_uuid()

    # SSOT：项目上下文以 shared_state 为准。请求体显式指定非 0 project_id
    # 时视为切换意图，同步更新 shared_state（持久化）；否则用权威值。
    from app.core.state import shared_state

    project_id = int(req.project_id) if req.project_id else 0
    if project_id:
        await shared_state.set_active_project_id(project_id)
    else:
        project_id = await shared_state.get_active_project_id()

    ctx = EvoContext(
        request_id=f"req-{req.thread_id}-{int(time.time())}",
        thread_id=req.thread_id,
        project_id=project_id,
        command_id=req.command_id,
        active_model=req.model,
        token=token,
    )
    if req.working_directory:
        thread_context_store.set_working_directory(req.thread_id, req.working_directory)
    member_id = _current_user.id if _current_user else 0

    async with route_lock_scope(req.thread_id, ctx):
        logger.debug("[ChatEndpoint] Run initialized for thread %s", req.thread_id)

        outcome = await dispatch_user_message(
            {**dict(req), "project_id": project_id},
            source="web",
            input_channel=web_input,
            thread_id=req.thread_id,
            project_id=project_id,
            member_id=member_id,
            context=ctx,
        )

        if outcome.handled:
            local_outcome = outcome.local_response

            # Map ActionOutcome to WebPresenter-compatible JSON response
            status = "done" if local_outcome.ok else "failed"
            summary = local_outcome.message

            response = {
                "status": status,
                "action_type": local_outcome.action_type,
                "summary": summary,
            }

            if local_outcome.action_type == "navigate":
                response["navigate"] = local_outcome.data.get("route")
            elif local_outcome.action_type == "macro":
                response["fell_back"] = local_outcome.data.get("fell_back", False)

            response["thread_id"] = req.thread_id

            await activity_monitor.end_run(
                req.thread_id,
                status="done",
                final_outcome=summary,
            )
            return response

        if outcome.msg is None:
            return JSONResponse({"error": "invalid request"}, status_code=400)

        dispatch_result = outcome.inputs
        if dispatch_result.status == "failed":
            raise HTTPException(status_code=500, detail=dispatch_result.error)

        # 会话模式：统一走 session_manager.submit 注入会话主循环
        from app.core.session.manager import session_manager

        await session_manager.submit(req.thread_id, dispatch_result.inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": dispatch_result.message_id,
    }


@router.post("/chat/mock", dependencies=[Depends(verify_guest_access)])
async def mock_chat(req: ChatRequest):
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    from app.api.routes.chat import SCENARIOS

    scenario = req.scenario or "happy_path"
    scenario_fn = SCENARIOS.get(scenario)
    if not scenario_fn:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario: {scenario}. Supported: {list(SCENARIOS.keys())}",
        )

    async def mock_publish():
        try:
            await scenario_fn(req.thread_id)
        except Exception as e:
            logger.error(f"Error in mock publishing: {e}", exc_info=True)

    asyncio.create_task(mock_publish())
    return {"status": "mocking", "thread_id": req.thread_id}


@router.post("/chat/stop", response_model=StopChatResponse)
async def stop_chat(req: ChatRequest):
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    # 统一走 session_manager.stop_agent（有会话 → session.stop；无会话 → stop_run + cancel_worker 双兜底）
    from app.core.session.manager import session_manager

    await session_manager.stop_agent(req.thread_id, "web_stop")
    return StopChatResponse(status="stopping", thread_id=req.thread_id)


@router.post("/agent/stop", response_model=StopChatResponse)
async def stop_all_agent(
    _token: TokenDepOptional = None,
    project_id: int | None = None,
    thread_id: str | None = None,
):
    """统一停止 Agent 活动（Esc ×2 触发），停止范围按上下文分级：

    1. ``thread_id``（优先）：只停该线程的活跃会话/宏任务（Web 窗口 Esc×2）。
    2. ``project_id``（无 thread）：停该项目的活跃会话/宏任务/值守。
    3. 无参数：全停（值守模式 Esc×2，停所有会话 + 宏 + 值守）。

    member_id 从 token 解析，用于按用户过滤会话（web/voice/mobile 共用）。
    """
    from app.core.channel.duty import provision
    from app.core.engine.worker_registry import worker_registry
    from app.core.identity import identity_service
    from app.core.session.manager import session_manager

    # 从 token 解析当前用户 member_id（用于按用户过滤会话）
    member_id = None
    if _token:
        try:
            member_id = await identity_service.resolve_member_id_from_token(_token)
        except Exception:
            logger.warning("[agent-stop] resolve member_id failed, stop without member filter", exc_info=True)

    if thread_id:
        # 只停当前线程（Web 窗口 Esc×2）
        await session_manager.stop_agent(thread_id, "esc_stop_thread")
    elif project_id is not None:
        # 停指定项目：session + 宏 + 值守
        await session_manager.stop_all(
            "esc_stop_project",
            project_id=project_id,
            member_id=member_id,
        )
        await worker_registry.cancel_all(project_id=project_id)
        try:
            await provision.stop_project(project_id)
        except Exception as e:
            logger.warning(f"[agent-stop] duty stop(project={project_id}) skipped: {e}", exc_info=True)
    else:
        # 全停（值守模式 Esc×2）
        await session_manager.stop_all("esc_stop", member_id=member_id)
        await worker_registry.cancel_all()
        try:
            await provision.stop_global()
        except Exception as e:
            logger.warning(f"[agent-stop] duty stop_global skipped: {e}", exc_info=True)
    return StopChatResponse(status="stopping", thread_id=thread_id or "")


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(
    req: ChatRequest,
    _request: Request = None,
    _current_user: CurrentUserOptional = None,
    token: TokenDepOptional = None,
):
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    from app.core.engine.rewind import (
        MessageNotFoundError,
        NoHumanMessageError,
        RewindError,
        perform_rewind,
    )

    async with session_scope() as session:
        if req.message_id:
            logger.info(f"[Retry] Targeted retry for message {req.message_id}")
            stmt = (
                select(Message)
                .options(selectinload(Message.references))
                .where(Message.id == req.message_id)
            )
            result = await session.execute(stmt)
            target_msg = result.scalar_one_or_none()

            if not target_msg:
                logger.warning(
                    f"[Retry] Message {req.message_id} not found in database"
                )
                raise HTTPException(
                    status_code=404, detail=f"Message {req.message_id} not found"
                )
            if target_msg.thread_id != req.thread_id:
                logger.warning(
                    f"[Retry] Message {req.message_id} belongs to thread {target_msg.thread_id}"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Message {req.message_id} not found in thread",
                )
            if target_msg.role != "human":
                logger.warning(
                    f"[Retry] Message {req.message_id} has role '{target_msg.role}'"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Message {req.message_id} is not a human message",
                )
            last_human_msg = target_msg
        else:
            stmt = (
                select(Message)
                .options(selectinload(Message.references))
                .where(Message.thread_id == req.thread_id)
                .where(Message.role == "human")
                .order_by(Message.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            last_human_msg = result.scalar_one_or_none()

        if not last_human_msg:
            raise HTTPException(
                status_code=404, detail="No human message found to retry"
            )

        references = None
        if last_human_msg.references:
            references = [
                {
                    "type": ref.type,
                    "id": ref.target_id,
                    "target_id": ref.target_id,
                    "target_name": ref.target_name,
                    "meta_data": ref.meta_data,
                }
                for ref in last_human_msg.references
            ]

        retry_message_content = last_human_msg.content

    try:
        result = await perform_rewind(
            thread_id=req.thread_id,
            target_message_id=str(last_human_msg.id),
            include_target=False,
            revert_files=req.revert_files,
            reset_state=True,
            reason="retry",
        )

        files_reverted = result.reverted_file_count
        checkpoint_id = None

        if result.status != "success":
            errors_str = "; ".join(result.errors)
            logger.error(f"[Retry] Rewind failed: {errors_str}")
            raise RewindError(errors_str, thread_id=req.thread_id)

        logger.info(
            f"[Retry] Rewind completed: {result.removed_message_count} messages removed, "
            f"{result.reverted_file_count} files reverted"
        )

    except MessageNotFoundError:
        raise HTTPException(
            status_code=404, detail="Target message not found for retry"
        )
    except NoHumanMessageError:
        raise HTTPException(status_code=404, detail="No human message found to retry")
    except RewindError as e:
        logger.exception(f"[Retry] Rewind failed: {e}")
        raise HTTPException(500, f"Rewind failed: {e}")
    except Exception as e:
        logger.exception(f"[Retry] Unexpected error during rewind: {e}")
        raise HTTPException(500, f"Retry failed: {e}")

    from app.core.state import shared_state

    project_id = int(req.project_id) if req.project_id else 0
    if project_id:
        await shared_state.set_active_project_id(project_id)
    else:
        project_id = await shared_state.get_active_project_id()

    ctx = EvoContext(
        thread_id=req.thread_id,
        project_id=project_id,
        active_model=req.model,
        token=token,
    )
    ContextManager.set(ctx)

    msg = await web_input.receive(
        {
            "thread_id": req.thread_id,
            "message": retry_message_content,
            "project_id": project_id,
            "references": references,
            "command_id": req.command_id,
            "checkpoint_id": checkpoint_id,
            "model": req.model,
        },
        context=ctx,
        member_id=_current_user.id if _current_user else 0,
        is_retry=True,
        skip_message_persistence=True,
    )
    if msg is None:
        raise HTTPException(status_code=400, detail="invalid retry request")
    result = await web_input.dispatch(msg)
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    # 会话模式：统一走 session_manager.submit（有活会话注入，无活会话创建并启动）
    from app.core.session.manager import session_manager

    await session_manager.submit(req.thread_id, result.inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": result.message_id,
        "action": "retry",
        "files_reverted": files_reverted,
    }


@router.post("/chat/resume")
async def resume_chat(
    req: ResumeRequest,
    bg_tasks: BackgroundTasks,
    _current_user: CurrentUserOptional = None,
    token: TokenDepOptional = None,
):
    active_model = req.model
    if not active_model:
        loaded_ctx = await ContextManager.load(req.thread_id)
        if loaded_ctx:
            active_model = loaded_ctx.active_model

    # 会话模式（§4.5）：有活会话 → 注入恢复/新输入，会话主循环处理；无活会话 → 原单发路径
    from app.core.session.manager import session_manager

    session = session_manager.get(req.thread_id)
    if session is not None and session.lifecycle == "running":
        from app.core.hitl.orchestrator import HITLOrchestrator

        pending = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)
        if pending:
            logger.info("[Chat] Resume into live session (HITL) %s", req.thread_id)
            session.inject_resume(
                req.user_input or "",
                project_id=pending.get("project_id") or req.project_id,
            )
        else:
            logger.info("[Chat] Resume as new message into live session %s", req.thread_id)
            from app.core.engine.dispatch import persist_user_message

            await persist_user_message(
                thread_id=req.thread_id,
                content=req.user_input or "",
                project_id=req.project_id,
                member_id=_current_user.id if _current_user else 0,
            )
            session.inject_user_message(
                {
                    "goal": req.user_input or "",
                    "project_id": req.project_id,
                    "model": active_model,
                    "metadata": {"token": token} if token else {},
                }
            )
        return ResumeChatResponse(status="resuming", thread_id=req.thread_id)

    from app.core.hitl.orchestrator import HITLOrchestrator

    pending_tool = await HITLOrchestrator.get_pending_request(
        req.thread_id, active_model
    )

    inputs = None

    if req.user_input and not pending_tool:
        try:
            parsed = json.loads(req.user_input)
            if isinstance(parsed, dict) and parsed.get("type") == "temp_project":
                temp_project_id = parsed.get("project_id")
                thread_context_store.set_temp_project(req.thread_id, temp_project_id)
                sel_msg = SystemToolsFormatter.signals([
                    f"Selected project: {parsed.get('project_name', temp_project_id)}"
                ])
                inputs = {"messages": [HumanMessage(content=sel_msg)]}
            else:
                inputs = {"messages": [HumanMessage(content=req.user_input)]}
        except json.JSONDecodeError:
            inputs = {"messages": [HumanMessage(content=req.user_input)]}

        ctx = ContextManager.current()
        if not ctx.token:
            ctx.token = token
            ContextManager.set(ctx)

        from app.core.engine.dispatch import persist_user_message

        await persist_user_message(
            thread_id=req.thread_id,
            content=req.user_input,
            project_id=req.project_id,
            member_id=_current_user.id if _current_user else 0,
        )

    if pending_tool:
        normalized_input = await HITLOrchestrator.handle_resume(req.thread_id, pending_tool, req.user_input)
        # 授权门控工具：审批后记录授权并用原始参数重执行，返回真实结果；
        # confirmation 类工具则直接使用归一化输入（APPROVED）。
        resume_config = {
            "configurable": {"thread_id": req.thread_id, "model": active_model},
            "metadata": {"project_id": req.project_id},
        }
        final_result = await HITLOrchestrator.resolve_approved_tool_result(
            pending_tool,
            resume_config,
            normalized_input
        )

        # 落为 human 消息（用户可见）+ 更新原 tool 消息结果（Agent 可见），
        # 而非新增 tool 消息——避免同一 tool_call 双 tool 结果导致 LLM 重建
        # 上下文取到空的旧 tool_output（HITL 选项未被 Agent 消费的问题）。
        await HITLOrchestrator.persist_hitl_user_message(
            thread_id=req.thread_id,
            project_id=req.project_id,
            member_id=_current_user.id if _current_user else 0,
            tool_call_id=pending_tool["id"],
            user_content=normalized_input,
            final_result=final_result,
        )

        # 恢复完整会话历史（含 assistant 的 tool_calls 声明与更新后的 tool
        # 结果配对）。原 tool 消息已被 update_content_by_tool_call_id 改写为
        # 最终结果，直接走 DB 历史即可，无需再 append tool_msg（否则又出现
        # 同一 tool_call 两条 tool 结果的错配）。
        try:
            from app.core.engine.message.repository import MessageRepository
            from app.core.engine.message.utils import to_base_message

            repo = MessageRepository(req.thread_id, project_id=req.project_id, member_id=_current_user.id if _current_user else 0)
            db_history, _, _ = await repo.get_full_history(limit=20)
            history_messages = [
                bm for bm in (to_base_message(m) for m in db_history) if bm is not None
            ]
            inputs = {"messages": history_messages}
        except Exception as e:
            logger.warning(f"[Chat] Resume history restore failed, falling back to single tool_msg: {e}")
            inputs = {"messages": [ToolMessage(tool_call_id=pending_tool["id"], content=final_result)]}

    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": active_model,
            "run_id": f"resume-{req.thread_id}-{int(time.time())}",
        },
        "metadata": {"project_id": req.project_id},
    }

    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(
            resume_graph_background,
            req.thread_id,
            inputs,
            config,
            run_label="Resuming...",
            clear_human_request_flag=True,
        )
    else:
        from app.core.engine.message.converter import EvoMessageConverter

        serialized_inputs = inputs.copy() if inputs else {}
        if "messages" in serialized_inputs:
            serialized_inputs["messages"] = EvoMessageConverter.repair(
                serialized_inputs["messages"]
            )

        from app.infrastructure.queue.factory import get_scheduler

        get_scheduler().send_task(
            "engine_resume_graph_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming...", True),
        )

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)
