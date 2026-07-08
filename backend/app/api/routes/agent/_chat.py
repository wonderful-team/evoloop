import asyncio
import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
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
from app.core.config import settings
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.graph_runner import resume_graph_background
from app.core.engine.message.native_classes import HumanMessage, ToolMessage
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database import session_scope
from app.models import Message
from app.models.learning import LearnedSkill
from app.utils.id import gen_uuid

router = APIRouter()

logger = logging.getLogger(__name__)

_thread_locks: dict[str, asyncio.Lock] = {}
_thread_locks_guard = asyncio.Lock()


async def _acquire_thread_lock(thread_id: str) -> asyncio.Lock:
    async with _thread_locks_guard:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


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
    bg_tasks: BackgroundTasks,
    _current_user: CurrentUserOptional,
    token: TokenDepOptional = None,
):
    if not req.thread_id:
        req.thread_id = gen_uuid()

    lock = await _acquire_thread_lock(req.thread_id)
    async with lock:
        await _check_thread_not_running(req.thread_id)

        await activity_monitor._state_service.start_run(
            req.thread_id, req.message or ""
        )

        ctx = EvoContext(
            request_id=f"req-{req.thread_id}-{int(time.time())}",
            thread_id=req.thread_id,
            project_id=req.project_id,
            command_id=req.command_id,
            active_model=req.model,
            token=token,
        )
        ContextManager.set(ctx)

        references = req.references or []
        if req.skill_ids:
            try:
                async with session_scope() as session:
                    stmt = select(LearnedSkill).where(
                        LearnedSkill.id.in_(req.skill_ids)
                    )
                    res = await session.execute(stmt)
                    skills = res.scalars().all()
                    for skill in skills:
                        references.append(
                            {
                                "id": str(skill.id),
                                "type": "skill",
                                "target_id": str(skill.id),
                                "target_name": skill.name,
                                "metadata": {
                                    "skill_id": skill.id,
                                    "skill_name": skill.name,
                                    "description": skill.description,
                                },
                                "meta_data": {
                                    "skill_id": skill.id,
                                    "skill_name": skill.name,
                                    "description": skill.description,
                                },
                            }
                        )
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"Failed to fetch skills {req.skill_ids}: {e}")

        logger.debug(f"[ChatEndpoint] Run initialized for thread {req.thread_id}")

        result = await dispatch_agent_run(
            thread_id=req.thread_id,
            message_content=req.message,
            project_id=req.project_id,
            references=references,
            command_id=req.command_id,
            checkpoint_id=req.checkpoint_id,
            model=req.model,
            context=ctx,
            member_id=_current_user.id if _current_user else 0,
        )
        if result.status == "failed":
            raise HTTPException(status_code=500, detail=result.error)

        bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": result.message_id,
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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Error in mock publishing: {e}", exc_info=True)

    asyncio.create_task(mock_publish())
    return {"status": "mocking", "thread_id": req.thread_id}


@router.post("/chat/stop", response_model=StopChatResponse)
async def stop_chat(req: ChatRequest):
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    await activity_monitor.stop_run(req.thread_id)
    return StopChatResponse(status="stopping", thread_id=req.thread_id)


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(
    req: ChatRequest,
    bg_tasks: BackgroundTasks,
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
                logger.warning(f"[Retry] Message {req.message_id} not found in database")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} not found")
            if target_msg.thread_id != req.thread_id:
                logger.warning(f"[Retry] Message {req.message_id} belongs to thread {target_msg.thread_id}")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} not found in thread")
            if target_msg.role != "human":
                logger.warning(f"[Retry] Message {req.message_id} has role '{target_msg.role}'")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} is not a human message")
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
            raise HTTPException(status_code=404, detail="No human message found to retry")

        references = None
        if last_human_msg.references:
            references = [
                {
                    "type": ref.type, "id": ref.target_id,
                    "target_id": ref.target_id, "target_name": ref.target_name,
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
        raise HTTPException(status_code=404, detail="Target message not found for retry")
    except NoHumanMessageError:
        raise HTTPException(status_code=404, detail="No human message found to retry")
    except RewindError as e:
        logger.error(f"[Retry] Rewind failed: {e}")
        raise HTTPException(500, f"Rewind failed: {e}")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"[Retry] Unexpected error during rewind: {e}")
        raise HTTPException(500, f"Retry failed: {e}")

    ctx = EvoContext(
        thread_id=req.thread_id,
        project_id=req.project_id,
        active_model=req.model,
        token=token,
    )
    ContextManager.set(ctx)

    result = await dispatch_agent_run(
        thread_id=req.thread_id,
        message_content=retry_message_content,
        project_id=req.project_id,
        references=references,
        command_id=req.command_id,
        checkpoint_id=checkpoint_id,
        model=req.model,
        is_retry=True,
        skip_message_persistence=True,
        context=ctx,
        member_id=_current_user.id if _current_user else 0,
        metadata={"goal_prefix": "Retry: "},
    )
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)

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

    from app.core.hitl.orchestrator import HITLOrchestrator

    pending_tool = await HITLOrchestrator.get_pending_request(req.thread_id, active_model)

    inputs = None
    if pending_tool:
        logger.info(f"Auto-completing tool call {pending_tool['name']} on resume")
        normalized_input = await HITLOrchestrator.handle_resume(req.thread_id, pending_tool, req.user_input)
        tool_msg = ToolMessage(tool_call_id=pending_tool["id"], content=normalized_input)
        inputs = {"messages": [tool_msg]}

    elif req.user_input:
        try:
            parsed = json.loads(req.user_input)
            if isinstance(parsed, dict) and parsed.get("type") == "temp_project":
                temp_project_id = parsed.get("project_id")
                thread_context_store.set_temp_project(req.thread_id, temp_project_id)
                from app.utils.controller_response import SystemToolsFormatter
                sel_msg = SystemToolsFormatter.signals(
                    [f"Selected project: {parsed.get('project_name', temp_project_id)}"]
                )
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
        tool_msg = ToolMessage(tool_call_id=pending_tool["id"], content=normalized_input)
        if inputs and "messages" in inputs:
            inputs["messages"] = [tool_msg]
        else:
            inputs = {"messages": [tool_msg]}

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
            resume_graph_background, req.thread_id, inputs, config,
            run_label="Resuming...", clear_human_request_flag=True,
        )
    else:
        from app.core.engine.message.converter import EvoMessageConverter
        serialized_inputs = inputs.copy() if inputs else {}
        if "messages" in serialized_inputs:
            serialized_inputs["messages"] = EvoMessageConverter.from_langchain(serialized_inputs["messages"])

        from app.infrastructure.queue.factory import get_scheduler
        get_scheduler().send_task(
            "engine_resume_graph_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming...", True),
        )

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)
