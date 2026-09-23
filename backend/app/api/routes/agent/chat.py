import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse

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
from app.core.engine.dispatch import DispatchStatus
from app.core.engine.message.native_classes import HumanMessage, ToolMessage
from app.core.engine.resume_runner import resume_agent_background
from app.core.execution.system_tools_formatter import SystemToolsFormatter
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.constants import ActivityStatus
from app.core.routing.dispatch_handler import dispatch_user_message, route_lock_scope
from app.utils.id import gen_uuid, unique_id

router = APIRouter()

logger = logging.getLogger(__name__)


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
        request_id=unique_id("req", req.thread_id),
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
                status=ActivityStatus.DONE,
                final_outcome=summary,
            )
            return response

        if outcome.msg is None:
            return JSONResponse({"error": "invalid request"}, status_code=400)

        dispatch_result = outcome.inputs
        if dispatch_result.status == DispatchStatus.FAILED:
            raise HTTPException(status_code=500, detail=dispatch_result.error)

        # 会话模式：统一走 session_manager.submit 注入会话主循环
        from app.core.engine.session.manager import session_manager

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
    # 统一走 session_manager.stop_agent（有会话 → session.stop；无会话 → stop_run + cancel_run 双兜底）
    from app.core.engine.session.manager import session_manager

    await session_manager.stop_agent(req.thread_id, "web_stop")
    try:
        from app.domain.tasks.service import TaskQueueService

        task = await TaskQueueService.get_task_by_thread(req.thread_id)
        if task and task.status == "in_progress":
            await TaskQueueService.edit_task(task.id, cancel=True)
    except Exception:
        logger.warning(
            "[stop_chat] cancel associated task failed for %s", req.thread_id, exc_info=True
        )
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
    from app.core.engine.agent_run_registry import agent_run_registry
    from app.core.engine.session.manager import session_manager
    from app.core.identity import identity_service

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
        await agent_run_registry.cancel_all(project_id=project_id)
        try:
            await provision.stop_project(project_id)
        except Exception as e:
            logger.warning(f"[agent-stop] duty stop(project={project_id}) skipped: {e}", exc_info=True)
    else:
        # 全停（值守模式 Esc×2）
        await session_manager.stop_all("esc_stop", member_id=member_id)
        await agent_run_registry.cancel_all()
        try:
            await provision.stop_global()
        except Exception as e:
            logger.warning(f"[agent-stop] duty stop_global skipped: {e}", exc_info=True)
    return StopChatResponse(status="stopping", thread_id=thread_id or "")


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(
    req: ChatRequest,
    _current_user: CurrentUserOptional = None,
    token: TokenDepOptional = None,
):
    """重试会话中最近/指定的一条 human 消息。

    定位消息、rewind、重派、submit 全部收敛到 retry_service（与
    EngineCommand 重派共用同一实现）：skip_l0=True、intent_hint 由
    统一路由产出、host_context 从被重试消息的持久化 meta_data 恢复。
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    from app.core.context.manager import ContextManager
    from app.core.engine.retry_service import RetryError, retry_and_redispatch
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

    try:
        outcome = await retry_and_redispatch(
            thread_id=req.thread_id,
            project_id=project_id,
            context=ctx,
            member_id=_current_user.id if _current_user else 0,
            target_message_id=req.message_id,
            host_context=req.host_context,
            revert_files=req.revert_files,
            reset_state=True,
            include_target=False,
            reason="retry",
            command_id=req.command_id,
            model=req.model,
            source="web",
        )
    except RetryError as e:
        raise HTTPException(status_code=e.status, detail=e.message)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": outcome.message_id,
        "action": "retry",
        "files_reverted": outcome.files_reverted,
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

    # SSOT：项目上下文以 shared_state 为准。请求体显式指定非 0 project_id
    # 时视为切换意图，同步更新 shared_state（持久化）；否则用权威值。
    from app.core.state import shared_state
    project_id = int(req.project_id) if req.project_id else 0
    if project_id:
        await shared_state.set_active_project_id(project_id)
    else:
        project_id = await shared_state.get_active_project_id()

    # 会话模式（§4.5）：有活会话 → 注入恢复/新输入，会话主循环处理；无活会话 → 原单发路径
    from app.core.engine.session.manager import session_manager

    session = session_manager.get(req.thread_id)
    if session is not None and session.lifecycle == "running":
        from app.core.hitl.orchestrator import HITLOrchestrator

        pending = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)
        if pending is None:
            # 竞态兜底：HITL 刚创建时 system Message（WAITING_HUMAN）落库有几毫秒
            # 延迟，超快到达的 resume（自动化客户端/值守）会查不到 pending 而被
            # 误降级为"新消息"——Agent 将收不到批准/拒绝反馈。仅当 human_requests
            # 存在 pending 审批时才轮询等待（真实新消息零延迟，不受影响）。
            from app.core.hitl.core import get_pending_requests_for_thread

            try:
                pending_rows = await get_pending_requests_for_thread(req.thread_id)
            except Exception:
                logger.warning(
                    "[Chat] pending approval rows lookup failed (thread=%s)",
                    req.thread_id,
                )
                pending_rows = []
            for _ in range(10):
                if not pending_rows:
                    break
                await asyncio.sleep(0.2)
                pending = await HITLOrchestrator.get_pending_request(
                    req.thread_id, active_model
                )
                if pending:
                    logger.info(
                        "[Chat] pending HITL message became ready after poll (thread=%s)",
                        req.thread_id,
                    )
                    break
        if pending:
            logger.info("[Chat] Resume into live session (HITL) %s", req.thread_id)
            session.inject_resume(
                req.user_input or "",
                project_id=pending.get("project_id") or project_id,
                grant_mode=req.grant_mode,
            )
        else:
            logger.info("[Chat] Resume as new message into live session %s", req.thread_id)
            from app.core.engine.dispatch import persist_user_message

            await persist_user_message(
                thread_id=req.thread_id,
                content=req.user_input or "",
                project_id=project_id,
                member_id=_current_user.id if _current_user else 0,
            )
            session.inject_user_message(
                {
                    "goal": req.user_input or "",
                    "project_id": project_id,
                    "model": active_model,
                    "metadata": {"token": token} if token else {},
                }
            )
        return ResumeChatResponse(status="resuming", thread_id=req.thread_id)

    from app.core.hitl.orchestrator import HITLOrchestrator

    pending_tool = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)

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
            project_id=project_id,
            member_id=_current_user.id if _current_user else 0,
        )

    if pending_tool:
        normalized_input, claimed = await HITLOrchestrator.handle_resume(
            req.thread_id, pending_tool, req.user_input, grant_mode=req.grant_mode
        )
        if not claimed:
            # 并发 resume 竞态：pending 已被其他端（手机/桌面/CLI）消费，
            # 重执行与 agent 恢复由消费方负责，此处不得重复执行（副作用×2）。
            logger.info(
                "[Chat] resume lost race for pending request (thread=%s, call=%s)",
                req.thread_id,
                pending_tool.get("id"),
            )
            return ResumeChatResponse(status="resuming", thread_id=req.thread_id)
        # 授权门控工具：审批后记录授权并用原始参数重执行，返回真实结果；
        # confirmation 类工具则直接使用归一化输入（APPROVED）。
        resume_config = {
            "configurable": {"thread_id": req.thread_id, "model": active_model},
            "metadata": {"project_id": project_id},
        }
        final_result = await HITLOrchestrator.resolve_approved_tool_result(
            pending_tool,
            resume_config,
            normalized_input,
            grant_mode=req.grant_mode,
            thread_id=req.thread_id,
        )

        # 落为 human 消息（用户可见）+ 更新原 tool 消息结果（Agent 可见），
        # 而非新增 tool 消息——避免同一 tool_call 双 tool 结果导致 LLM 重建
        # 上下文取到空的旧 tool_output（HITL 选项未被 Agent 消费的问题）。
        # 用户可见文案按"点了什么存什么"：中文界面落中文（批准/拒绝），英文
        # 界面落英文（Approve/Reject）；normalized 只用于内部决策。
        await HITLOrchestrator.persist_hitl_user_message(
            thread_id=req.thread_id,
            project_id=project_id,
            member_id=_current_user.id if _current_user else 0,
            tool_call_id=pending_tool["id"],
            user_content=req.user_input or normalized_input,
            final_result=final_result,
        )

        # 恢复完整会话历史（含 assistant 的 tool_calls 声明与更新后的 tool
        # 结果配对）。原 tool 消息已被 update_content_by_tool_call_id 改写为
        # 最终结果，直接走 DB 历史即可，无需再 append tool_msg（否则又出现
        # 同一 tool_call 两条 tool 结果的错配）。
        try:
            from app.core.engine.message.repository import MessageRepository
            from app.core.engine.message.utils import to_base_message

            repo = MessageRepository(req.thread_id, project_id=project_id, member_id=_current_user.id if _current_user else 0)
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
            "run_id": unique_id("resume", req.thread_id),
        },
        "metadata": {"project_id": project_id},
    }

    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(
            resume_agent_background,
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
            # native → JSON-safe dict：Celery 传输不接受原生消息对象
            # （EncodeError: HumanMessage is not JSON serializable）。
            serialized_inputs["messages"] = EvoMessageConverter.to_transport(
                EvoMessageConverter.repair(serialized_inputs["messages"])
            )

        from app.infrastructure.queue.factory import get_scheduler

        get_scheduler().send_task(
            "engine_resume_agent_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming...", True),
        )

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)
