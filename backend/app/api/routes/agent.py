import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserOptional,
    TokenDepOptional,
    verify_guest_access,
)
from app.api.schemas.agent import (
    ChatRequest, WebhookRequest, ResumeRequest, CancelHITLRequest,
    StopChatResponse, ResumeChatResponse, CancelHITLResponse, WebhookResponse
)
from app.core.config import settings
from app.core.context import thread_context_store
from app.core.context.manager import ContextManager, EvoContext
from app.constants import DEFAULT_PROJECT_ID
# --- Background Worker ---
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.graph_runner import resume_graph_background
from app.core.engine.tasks import run_agent_background_task
from app.core.evocloud import evocloud_manager
from app.core.globals import get_graph
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.codebase.indexing.service import IndexingService
from app.domain.integration.adapters import EventAdapter
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.models.learning import LearnedSkill
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Unified Dispatch Helpers
# =============================================================================

@router.post("/chat", dependencies=[Depends(verify_guest_access)])
async def chat_endpoint(req: ChatRequest, bg_tasks: BackgroundTasks, _current_user: CurrentUserOptional, token: TokenDepOptional = None):
    """
    Unified entry point for User Chat (Local Background Task).
    """
    if not req.thread_id:
        req.thread_id = str(uuid.uuid4())

    ctx = EvoContext(
        request_id=f"req-{req.thread_id}-{int(time.time())}",
        thread_id=req.thread_id,
        project_id=req.project_id,
        command_id=req.command_id,
        active_model=req.model,
        token=token
    )
    ContextManager.set(ctx)

    # Process skill_ids if provided
    references = req.references or []
    if req.skill_ids:
        try:
            async with session_scope() as session:
                stmt = select(LearnedSkill).where(LearnedSkill.id.in_(req.skill_ids))
                res = await session.execute(stmt)
                skills = res.scalars().all()
                for skill in skills:
                    references.append({
                        "id": str(skill.id),
                        "type": "skill",
                        "target_id": str(skill.id),
                        "target_name": skill.name,
                        "metadata": {
                            "skill_id": skill.id,
                            "skill_name": skill.name,
                            "description": skill.description
                        },
                        "meta_data": {  # 保留兼容，供外部旧的解析逻辑取用
                            "skill_id": skill.id,
                            "skill_name": skill.name,
                            "description": skill.description
                        }
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch skills {req.skill_ids}: {e}")

    logger.debug(f"[ChatEndpoint] Run initialized for thread {req.thread_id}")

    # Use Unified Dispatcher
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

    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)
    else:
        # Use jsonable_encoder to ensure Pydantic models (like MessageBlock) with UUIDs/datetimes are fully JSON serializable
        from fastapi.encoders import jsonable_encoder
        serialized_inputs = jsonable_encoder(result.inputs.model_dump())
        run_agent_background_task.delay(req.thread_id, serialized_inputs)

    return {"status": "queued", "thread_id": req.thread_id, "message_id": result.message_id}


@router.post("/chat/mock", dependencies=[Depends(verify_guest_access)])
async def mock_chat(req: ChatRequest):
    """
    Simulate a mock chat execution by publishing directly to the event bus.
    Supports scenarios: happy_path, hitl, quota_exhausted, long_task.
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    from app.core.monitoring.activity import activity_monitor
    from app.core.engine.message.handler import MessageHandler
    from app.core.engine.message.factory import MessageBlockFactory
    from app.core.engine.message.publisher import MessagePublisher
    from app.models.schemas.events import QuotaExhaustedEvent, StatusEvent
    from app.core.engine.message.schemas import ReferenceBlock
    from app.core.engine.message.category import MessageCategory
    import asyncio
    import datetime

    scenario = req.scenario or "happy_path"
    now_str = datetime.datetime.utcnow().isoformat() + "Z"

    async def mock_publish():
        # Helper to publish an AI thinking message with tool calls (representing Supervisor's decision)
        async def publish_ai_tool_call(seq_num: int, tool_name: str, tool_args: dict, call_id: str, run_id: str):
            publisher = MessagePublisher(req.thread_id)
            msg_block = MessageBlockFactory.from_event(
                thread_id=req.thread_id,
                sequence_number=seq_num,
                role="ai",
                content="",
                category="ai_response",
                status="completed",
                run_id=run_id,
                tool_calls=[{
                    "id": call_id,
                    "name": tool_name,
                    "args": tool_args,
                    "type": "tool_call"
                }]
            )
            await publisher.publish(msg_block)
            await asyncio.sleep(0.4)

        # Helper to publish a tool starting event (status="running")
        async def publish_tool_start(seq_num: int, tool_name: str, call_id: str, input_args: dict, run_id: str):
            publisher = MessagePublisher(req.thread_id)
            tool_block = MessageBlockFactory.from_event(
                thread_id=req.thread_id,
                sequence_number=seq_num,
                role="tool",
                content="",
                category="tool_output",
                status="running",
                run_id=run_id,
                tool_name=tool_name,
                tool_call_id=call_id,
                metadata={"input": input_args}
            )
            await publisher.publish(tool_block)
            await asyncio.sleep(0.4)

        # Helper to publish a tool output event (status="completed")
        async def publish_tool_output(seq_num: int, tool_name: str, call_id: str, input_args: dict, output_content: str, run_id: str):
            publisher = MessagePublisher(req.thread_id)
            tool_block = MessageBlockFactory.from_event(
                thread_id=req.thread_id,
                sequence_number=seq_num,
                role="tool",
                content=output_content,
                category="tool_output",
                status="completed",
                run_id=run_id,
                tool_name=tool_name,
                tool_call_id=call_id,
                metadata={"input": input_args, "output": output_content}
            )
            await publisher.publish(tool_block)
            await asyncio.sleep(0.4)

        try:
            if scenario == "happy_path":
                # Initialize run
                run_id = f"run-mock-{uuid.uuid4().hex[:8]}"
                await activity_monitor.start_run(req.thread_id, main_goal="正常流式对话模拟", run_id=run_id)
                await asyncio.sleep(0.5)

                # Supervisor PLANNING - Turn 1
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="分析项目结构以确定 UI 组件位置..."
                )
                await asyncio.sleep(0.5)

                # Stream thinking
                thinking_text = "根据用户提出的任务，我需要先扫描前端组件目录结构，寻找可用的 Button 组件。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # AI decides to call list_dir (seq=2)
                await publish_ai_tool_call(2, "list_dir", {"DirectoryPath": "frontend/src/components"}, "call_ld1", run_id)

                # Transition to Worker EXECUTING - Turn 1
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: list_dir",
                    task_status="正在读取 frontend/src/components 目录..."
                )

                # Emit tool start (seq=3, status="running")
                await publish_tool_start(3, "list_dir", "call_ld1", {"DirectoryPath": "frontend/src/components"}, run_id)
                await MessageHandler.stream_progress(req.thread_id, "正在获取目录中的文件列表...", progress=50, status="running")
                await asyncio.sleep(0.5)

                # Emit tool output (seq=3, status="completed")
                dir_output = "['Button.tsx', 'Header.tsx', 'Footer.tsx']"
                await publish_tool_output(3, "list_dir", "call_ld1", {"DirectoryPath": "frontend/src/components"}, dir_output, run_id)
                await MessageHandler.stream_progress(req.thread_id, "目录列表读取成功。", progress=100, status="success")
                await asyncio.sleep(0.5)

                # Supervisor PLANNING - Turn 2
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="找到 Button.tsx，准备读取文件内容..."
                )
                await asyncio.sleep(0.5)

                # Stream thinking
                thinking_text = "我已找到 Button.tsx 文件。现在我将读取它的代码内容以了解目前的属性定义。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # AI decides to call read_file (seq=4)
                await publish_ai_tool_call(4, "read_file", {"AbsolutePath": "frontend/src/components/Button.tsx"}, "call_rf1", run_id)

                # Worker EXECUTING - Turn 2
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: read_file",
                    task_status="正在读取 frontend/src/components/Button.tsx..."
                )

                # Emit tool start (seq=5, status="running")
                await publish_tool_start(5, "read_file", "call_rf1", {"AbsolutePath": "frontend/src/components/Button.tsx"}, run_id)
                await asyncio.sleep(0.5)

                # Emit tool output (seq=5, status="completed")
                file_content = "export function Button({ label }: { label: string }) {\n  return <button className='btn'>{label}</button>;\n}"
                await publish_tool_output(5, "read_file", "call_rf1", {"AbsolutePath": "frontend/src/components/Button.tsx"}, file_content, run_id)
                await asyncio.sleep(0.5)

                # Supervisor PLANNING - Turn 3
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="分析代码并执行修改..."
                )
                await asyncio.sleep(0.5)

                # Stream thinking
                thinking_text = "Button 组件目前的属性只支持 label。我需要支持 onClick 属性，并添加对应的点击回调类型。我将使用 replace_file_content 替换它。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # AI decides to call replace_file_content (seq=6)
                await publish_ai_tool_call(6, "replace_file_content", {"TargetFile": "frontend/src/components/Button.tsx"}, "call_rfc1", run_id)

                # Worker EXECUTING - Turn 3
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: replace_file_content",
                    task_status="正在应用替换逻辑..."
                )

                # Emit tool start (seq=7, status="running")
                await publish_tool_start(7, "replace_file_content", "call_rfc1", {"TargetFile": "frontend/src/components/Button.tsx"}, run_id)
                await asyncio.sleep(0.5)

                # Emit tool output (seq=7, status="completed")
                await publish_tool_output(7, "replace_file_content", "call_rfc1", {"TargetFile": "frontend/src/components/Button.tsx"}, "File contents replaced successfully.", run_id)
                await asyncio.sleep(0.5)

                # Supervisor PLANNING - Turn 4
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="编译检查与构建校验..."
                )
                await asyncio.sleep(0.5)

                # Stream thinking
                thinking_text = "文件修改已完成。我将运行编译命令 npm run build 确保类型无误且项目成功构建。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # AI decides to call run_command (seq=8)
                await publish_ai_tool_call(8, "run_command", {"CommandLine": "npm run build"}, "call_rc1", run_id)

                # Worker EXECUTING - Turn 4
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: run_command",
                    task_status="正在执行 npm run build..."
                )

                # Emit tool start (seq=9, status="running")
                await publish_tool_start(9, "run_command", "call_rc1", {"CommandLine": "npm run build"}, run_id)
                await MessageHandler.stream_progress(req.thread_id, "Building application bundles...", progress=75, status="running")
                await asyncio.sleep(0.8)

                # Emit tool output (seq=9, status="completed")
                await publish_tool_output(9, "run_command", "call_rc1", {"CommandLine": "npm run build"}, "vite v5.0.0 building...\nbuilt in 350ms.\n✓ 15 modules transformed.", run_id)
                await MessageHandler.stream_progress(req.thread_id, "编译构建通过。", progress=100, status="success")
                await asyncio.sleep(0.5)

                # Supervisor PLANNING - Final Answer
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="生成最终答复..."
                )
                await asyncio.sleep(0.5)

                answer_thinking = "我将向用户反馈 Button.tsx 文件的修改已完成，并且已通过 Vite 构建编译测试。\n"
                for char in answer_thinking:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                answer_content = "你好！我已为您完成了对 `Button.tsx` 的读取与重构，并成功执行了项目编译构建检验 (`npm run build`)，无类型冲突和构建错误。"
                for char in answer_content:
                    await MessageHandler.stream_token(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # Emit final message (seq=10)
                publisher = MessagePublisher(req.thread_id)
                msg_block = MessageBlockFactory.from_event(
                    thread_id=req.thread_id,
                    sequence_number=10,
                    role="ai",
                    content=answer_content,
                    thinking=answer_thinking,
                    category="ai_response",
                    status="completed",
                    run_id=run_id
                )
                await publisher.publish(msg_block)
                await asyncio.sleep(0.5)

                # End run
                await activity_monitor.end_run(req.thread_id, status="done", final_outcome="完成代码修改与校验", run_id=run_id)

            elif scenario == "hitl":
                run_id = f"run-mock-{uuid.uuid4().hex[:8]}"
                await activity_monitor.start_run(req.thread_id, main_goal="安全审批拦截模拟", run_id=run_id)
                await asyncio.sleep(0.5)

                # Supervisor PLANNING
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Decision",
                    task_status="评估生产环境上线环境..."
                )
                await asyncio.sleep(0.5)

                thinking_text = "检测到发布任务，我将运行生产环境上线部署脚本。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # AI decides to call run_command (seq=2)
                await publish_ai_tool_call(2, "run_command", {"CommandLine": "npm run deploy:production"}, "call_dep1", run_id)

                # Worker EXECUTING
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: run_command",
                    task_status="正在执行 npm run deploy:production..."
                )

                # Emit tool start (seq=3, status="running")
                await publish_tool_start(3, "run_command", "call_dep1", {"CommandLine": "npm run deploy:production"}, run_id)
                await MessageHandler.stream_progress(req.thread_id, "正在建立 SSH 连接并同步打包文件...", progress=40, status="running")
                await asyncio.sleep(0.8)

                # Safety interruption
                await MessageHandler.stream_progress(
                    thread_id=req.thread_id,
                    message="[安全拦截] 检测到高危写操作指令，部署至生产环境需要获得项目管理员授权审批。",
                    progress=40,
                    status="interrupted"
                )
                await activity_monitor.request_human_interaction(
                    thread_id=req.thread_id,
                    request_type="approval",
                    prompt="检测到即将执行部署脚本，是否批准部署至生产环境？",
                    payload={"context": "生产服务器：aws-prod-01, 目标版本：v2.1.0"},
                    allow_cancel=True
                )

                # Wait 4 seconds to let the user view the approval dialog
                await asyncio.sleep(4.0)

                # Simulate automatic approval from the user
                await activity_monitor.clear_human_request(req.thread_id)

                # Worker EXECUTING resumes
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="EXECUTING",
                    task_name="Worker: run_command",
                    task_status="用户已批准部署，正在恢复运行部署命令..."
                )

                # Re-emit tool start (status="running")
                await publish_tool_start(3, "run_command", "call_dep1", {"CommandLine": "npm run deploy:production"}, run_id)
                await MessageHandler.stream_progress(req.thread_id, "SSH 连接已恢复，正在传输构建制品包...", progress=80, status="running")
                await asyncio.sleep(1.0)

                # Emit tool output (status="completed")
                deploy_output = "Assets uploaded successfully.\nRunning health checks on remote server aws-prod-01...\nHealth check: PASSED (200 OK)"
                await publish_tool_output(3, "run_command", "call_dep1", {"CommandLine": "npm run deploy:production"}, deploy_output, run_id)
                await MessageHandler.stream_progress(req.thread_id, "生产发布成功！", progress=100, status="success")
                await asyncio.sleep(0.5)

                # Supervisor PLANNING
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Decision",
                    task_status="生成上线总结报告..."
                )
                await asyncio.sleep(0.5)

                answer_thinking = "部署已成功完成，现在生成用户可读的上线确认报告。\n"
                for char in answer_thinking:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                answer_content = "项目已成功发布至生产环境 (`aws-prod-01`)！所有服务已在线并处于健康运行状态。"
                for char in answer_content:
                    await MessageHandler.stream_token(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # Emit final message (seq=4)
                publisher = MessagePublisher(req.thread_id)
                msg_block = MessageBlockFactory.from_event(
                    thread_id=req.thread_id,
                    sequence_number=4,
                    role="ai",
                    content=answer_content,
                    thinking=answer_thinking,
                    category="ai_response",
                    status="completed",
                    run_id=run_id
                )
                await publisher.publish(msg_block)
                await asyncio.sleep(0.5)

                await activity_monitor.end_run(req.thread_id, status="done", final_outcome="完成生产环境部署", run_id=run_id)

            elif scenario == "quota_exhausted":
                run_id = f"run-mock-{uuid.uuid4().hex[:8]}"
                await activity_monitor.start_run(req.thread_id, main_goal="配额异常检测模拟", run_id=run_id)
                await asyncio.sleep(0.5)

                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Decision",
                    task_status="正在调度推理模型..."
                )
                await asyncio.sleep(1.0)

                thinking_text = "正在尝试调用大语言模型进行方案制定...\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.5)

                publisher = MessagePublisher(req.thread_id)

                # 1. Publish QuotaExhaustedEvent
                await publisher.publish(QuotaExhaustedEvent(
                    thread_id=req.thread_id,
                    title="配额已耗尽",
                    message="您当前的 LLM 账户使用配额已用完，无法继续处理请求。",
                    hint="请联系系统管理员添加配额，或在系统设置中更换您的 API 密钥。"
                ))
                await asyncio.sleep(0.5)

                # 2. Publish a system/ai message displaying the error
                error_content = "**配额已耗尽**\n您当前的 LLM 账户使用配额已用完，无法继续处理请求。\n\n*Hint: 请联系系统管理员添加配额，或在系统设置中更换您的 API 密钥。*"
                msg_block = MessageBlockFactory.from_event(
                    thread_id=req.thread_id,
                    sequence_number=3,
                    role="ai",
                    content=error_content,
                    category=MessageCategory.ERROR_SYSTEM.value,
                    status="failed",
                    run_id=run_id
                )
                await publisher.publish(msg_block)
                await asyncio.sleep(0.5)

                # 3. Publish StatusEvent (status="error")
                await publisher.publish(StatusEvent(thread_id=req.thread_id, status="error"))
                await asyncio.sleep(0.5)

                # 4. End run with status failed
                await activity_monitor.end_run(req.thread_id, status="failed", final_outcome="因配额耗尽中断执行", run_id=run_id)

            elif scenario == "long_task":
                run_id = f"run-mock-{uuid.uuid4().hex[:8]}"
                await activity_monitor.start_run(req.thread_id, main_goal="长程深度代码搜索与分析任务模拟", run_id=run_id)
                await asyncio.sleep(0.5)

                # Supervisor PLANNING
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Plan",
                    task_status="制定代码分析计划..."
                )
                await asyncio.sleep(0.8)

                thinking_text = "用户要求进行一次全库深度的依赖树检索，我需要拆分成多个子任务，首先交由 Worker 逐个目录进行 `grep_search` 和 `read_file`。\n"
                for char in thinking_text:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                # Loop to generate dozens of tool calls
                for i in range(1, 13): # Generate 12 tool calls
                    # AI decides to call a tool
                    tool_name = "grep_search" if i % 2 != 0 else "read_file"
                    tool_args = {"Query": f"dependency_{i}"} if i % 2 != 0 else {"AbsolutePath": f"src/module_{i}.ts"}
                    call_id = f"call_loop_{i}"
                    seq_base = i * 2

                    thinking_iter = f"\n准备执行第 {i} 步检索，调用 {tool_name}...\n"
                    for char in thinking_iter:
                        await MessageHandler.stream_thinking(req.thread_id, char)
                        await asyncio.sleep(0.01)

                    await publish_ai_tool_call(seq_base, tool_name, tool_args, call_id, run_id)

                    # Worker EXECUTING
                    await activity_monitor.update_agent_state(
                        thread_id=req.thread_id,
                        mode="EXECUTING",
                        task_name=f"Worker: Code Search {i}",
                        task_status=f"正在执行深度检索 ({i}/12)..."
                    )

                    # Emit tool start
                    await publish_tool_start(seq_base + 1, tool_name, call_id, tool_args, run_id)
                    await MessageHandler.stream_progress(req.thread_id, f"正在搜索模块 {i}...", progress=(i*100//12), status="running")
                    await asyncio.sleep(0.6)

                    # Emit tool output
                    tool_out = f"Found matches for query in module_{i}.ts lines 10-25.\n" if i % 2 != 0 else f"export const mod_{i} = require('lib_{i}');"
                    await publish_tool_output(seq_base + 1, tool_name, call_id, tool_args, tool_out, run_id)
                    await asyncio.sleep(0.4)

                # Supervisor PLANNING for final answer
                await activity_monitor.update_agent_state(
                    thread_id=req.thread_id,
                    mode="PLANNING",
                    task_name="Supervisor Decision",
                    task_status="正在汇总检索结果..."
                )
                await asyncio.sleep(0.5)

                answer_thinking = "检索结束，总计调用了数十次工具。现在我将向用户汇报汇总结果。\n"
                for char in answer_thinking:
                    await MessageHandler.stream_thinking(req.thread_id, char)
                    await asyncio.sleep(0.01)

                answer_content = "经过对整个代码库的数十次深度检索与阅读，我已经梳理清楚了您所需要的复杂依赖关系树！\n您可以查看上方的检索过程记录。"
                for char in answer_content:
                    await MessageHandler.stream_token(req.thread_id, char)
                    await asyncio.sleep(0.01)

                publisher = MessagePublisher(req.thread_id)
                msg_block = MessageBlockFactory.from_event(
                    thread_id=req.thread_id,
                    sequence_number=100,
                    role="ai",
                    content=answer_content,
                    thinking=answer_thinking,
                    category="ai_response",
                    status="completed",
                    run_id=run_id
                )
                await publisher.publish(msg_block)
                await asyncio.sleep(0.5)

                await activity_monitor.end_run(req.thread_id, status="done", final_outcome="完成全库深度搜索分析", run_id=run_id)

        except Exception as e:
            logger.error(f"Error in mock publishing: {e}", exc_info=True)

    # Run the mock publication in background so we don't block the HTTP request
    asyncio.create_task(mock_publish())
    return {"status": "mocking", "thread_id": req.thread_id}


@router.post("/chat/stop", response_model=StopChatResponse)
async def stop_chat(req: ChatRequest):
    """
    Stop the current generation for a thread.
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    await activity_monitor.stop_run(req.thread_id)
    return StopChatResponse(status="stopping", thread_id=req.thread_id)


@router.post("/chat/retry", dependencies=[Depends(verify_guest_access)])
async def retry_chat(req: ChatRequest, bg_tasks: BackgroundTasks, _request: Request = None, _current_user: CurrentUserOptional = None, token: TokenDepOptional = None):
    """
    Retry a specific user message (Targeted Retry).
    Rolls back history (deletes messages after the target) and restarts generation.

    Uses the new event-driven RewindOrchestrator for distributed cleanup.
    """
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    from app.core.engine.rewind import RewindOrchestrator
    from app.core.engine.rewind.exceptions import MessageNotFoundError, NoHumanMessageError, RewindError

    # =============================================================================
    # Phase 1: Rewind (Retry-Specific)
    # =============================================================================

    async with session_scope() as session:
        # Determine target message
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
                logger.warning(f"[Retry] Message {req.message_id} belongs to thread {target_msg.thread_id}, not {req.thread_id}")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} not found in thread")
            if target_msg.role != "human":
                logger.warning(f"[Retry] Message {req.message_id} has role '{target_msg.role}', not 'human'")
                raise HTTPException(status_code=404, detail=f"Message {req.message_id} is not a human message")
            last_human_msg = target_msg
        else:
            # Fallback to last human message
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

        # Load references for reconstruction
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

    # Perform Rewind using new event-driven RewindOrchestrator
    try:
        # Create orchestrator on-demand (stateless, lightweight)
        from app.core.events import system_bus
        orchestrator = RewindOrchestrator(event_bus=system_bus)

        # Perform rewind with retry-specific parameters
        result = await orchestrator.perform_rewind(
            thread_id=req.thread_id,
            target_message_id=str(last_human_msg.id),
            include_target=False,  # Retry specific: Keep the human message
            revert_files=req.revert_files,
            reset_state=True,      # Retry specific: Reset state for clean generation
            reason="retry"
        )

        files_reverted = result.reverted_file_count
        # Note: checkpoint_id is not directly available from new orchestrator
        # State reset is handled by StateRewind handler
        checkpoint_id = None

        # Verify rewind success before proceeding with retry
        if result.status != "success":
            errors_str = "; ".join(result.errors)
            error_msg = f"Rewind failed for retry: {errors_str}"
            logger.error(f"[Retry] {error_msg}")
            # Raise RewindError which is caught below to return 500
            from app.core.engine.rewind.exceptions import RewindError
            raise RewindError(error_msg, thread_id=req.thread_id)

        logger.info(f"[Retry] Rewind completed: {result.removed_message_count} messages removed, {result.reverted_file_count} files reverted")

    except MessageNotFoundError:
        raise HTTPException(status_code=404, detail="Target message not found for retry")
    except NoHumanMessageError:
        raise HTTPException(status_code=404, detail="No human message found to retry")
    except RewindError as e:
        logger.error(f"[Retry] Rewind failed: {e}")
        raise HTTPException(500, f"Rewind failed: {e}")
    except Exception as e:
        logger.error(f"[Retry] Unexpected error during rewind: {e}")
        raise HTTPException(500, f"Retry failed: {e}")

    # =============================================================================
    # Phase 2: Unified Dispatch (Shared with Chat)
    # =============================================================================
    # Setup Context
    ctx = EvoContext(
        thread_id=req.thread_id,
        project_id=req.project_id,
        active_model=req.model,
        token=token
    )
    ContextManager.set(ctx)

    # Use unified dispatcher
    # Note: checkpoint_id is None for new event-driven orchestrator
    # State reset is handled by StateRewind handler

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
        goal_prefix="Retry: ",
        context=ctx,
        member_id=_current_user.id if _current_user else 0,
    )
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)
    # if settings.EMBEDDED_MODE:
    #     bg_tasks.add_task(run_agent_background, req.thread_id, result.inputs)
    # else:
    #     run_agent_background_task.delay(req.thread_id, result.inputs)

    return {
        "status": "queued",
        "thread_id": req.thread_id,
        "message_id": result.message_id,
        "action": "retry",
        "files_reverted": files_reverted,
    }


@router.post("/chat/resume")
async def resume_chat(req: ResumeRequest, bg_tasks: BackgroundTasks, _current_user: CurrentUserOptional = None, token: TokenDepOptional = None):
    """
    Resume a paused/interrupted graph execution.
    Used after Human-in-the-Loop interrupts where user provides input.
    """
    graph = get_graph()
    checkpointer = db_resource_manager.checkpointer

    if not graph or not checkpointer:
        raise HTTPException(status_code=500, detail="Graph or Checkpointer not initialized")

    # Config for resuming from checkpoint
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "model": req.model,
            "run_id": f"run-resume-{gen_uuid()[:8]}",
        }
    }

    # Prepare input - if user provided input, add as message
    inputs = None
    if req.user_input:
        # Check if user_input contains temporary project context (Scheme C)
        try:
            parsed = json.loads(req.user_input)
            if isinstance(parsed, dict) and parsed.get("type") == "temp_project":
                temp_project_id = parsed.get("project_id")
                # Store temporary project for this thread
                thread_context_store.set_temp_project(req.thread_id, temp_project_id)
                # Use empty input for actual resume (the project is now in context)
                # Use system_tools template for selection message
                from app.utils import SystemToolsFormatter
                sel_msg = SystemToolsFormatter.signals([f"Selected project: {parsed.get('project_name', temp_project_id)}"])
                inputs = {"messages": [HumanMessage(content=sel_msg)]}
            else:
                inputs = {"messages": [HumanMessage(content=req.user_input)]}
        except json.JSONDecodeError:
            inputs = {"messages": [HumanMessage(content=req.user_input)]}

        # Context setup explicitly needed for persistence inside resume
        ctx = ContextManager.current()
        if not getattr(ctx, 'token', None):
            ctx.token = token
            ContextManager.set(ctx)

        # Persistence (shared with /chat and /retry via dispatch layer)
        from app.core.engine.dispatch import persist_user_message
        await persist_user_message(
            thread_id=req.thread_id,
            content=req.user_input,
            project_id=req.project_id,
            command_id=req.command_id,
            member_id=_current_user.id if _current_user else 0,
        )

    # [HITL Resume Fix]: Check if we need to auto-complete a Tool Call
    from app.core.engine.hitl import HITLOrchestrator
    pending_tool = await HITLOrchestrator.get_pending_request(graph, req.thread_id, req.model)
    
    if pending_tool:
        logger.info(f"Auto-completing tool call {pending_tool['name']} on resume")
        normalized_input = await HITLOrchestrator.handle_resume(req.thread_id, pending_tool, req.user_input)
        
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content=normalized_input,
        )

        if inputs and "messages" in inputs:
            inputs["messages"] = [tool_msg]
        else:
            inputs = {"messages": [tool_msg]}

    # Build Config
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "run_id": f"resume-{req.thread_id}-{int(time.time())}"
        },
        "metadata": {
            "project_id": req.project_id
        }
    }

    # Resume in background (unified resumption loop)
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
            serialized_inputs["messages"] = EvoMessageConverter.from_langchain(serialized_inputs["messages"])
            
        from app.infrastructure.queue.factory import get_scheduler
        get_scheduler().send_task(
            "engine_resume_graph_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming...", True)
        )

    return ResumeChatResponse(status="resuming", thread_id=req.thread_id)


@router.post("/hitl/cancel")
async def cancel_hitl_request(req: CancelHITLRequest, bg_tasks: BackgroundTasks):
    """
    Cancel a pending HITL (Human-in-the-Loop) request.
    This will dismiss the confirmation card and resume execution with a cancellation signal.
    """
    graph = get_graph()
    checkpointer = db_resource_manager.checkpointer

    if not graph or not checkpointer:
        raise HTTPException(
            status_code=500, detail="Graph or Checkpointer not initialized"
        )

    # [HITL Cancel Fix]: Send cancellation as ToolMessage instead of HumanMessage
    from app.core.engine.hitl import HITLOrchestrator
    pending_tool = await HITLOrchestrator.get_pending_request(graph, req.thread_id, req.model)
    
    # [HITL Closure]: Clear human request from activity monitor
    await activity_monitor.clear_human_request(req.thread_id)

    if not pending_tool:
        # Check if there was a transient activity request (non-graph)
        return CancelHITLResponse(
            status="cancelled",
            thread_id=req.thread_id,
            request_id=None,
        )

    logger.info(f"Auto-cancelling tool call {pending_tool['name']} on cancel")
    await HITLOrchestrator.handle_cancel(req.thread_id, pending_tool)

    tool_msg = ToolMessage(
        tool_call_id=pending_tool["id"],
        content="CANCELLED",
    )
    inputs = {"messages": [tool_msg]}

    # Build Config
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "run_id": f"cancel-{req.thread_id}-{int(time.time())}"
        },
        "metadata": {
            "project_id": req.project_id
        }
    }

    # Resume in background with cancellation signal (unified resumption loop)
    if settings.EMBEDDED_MODE:
        bg_tasks.add_task(
            resume_graph_background,
            req.thread_id,
            inputs,
            config,
            run_label="Resuming after cancellation...",
        )
    else:
        from app.core.engine.message.converter import EvoMessageConverter
        serialized_inputs = inputs.copy() if inputs else {}
        if "messages" in serialized_inputs:
            serialized_inputs["messages"] = EvoMessageConverter.from_langchain(serialized_inputs["messages"])
            
        from app.infrastructure.queue.factory import get_scheduler
        get_scheduler().send_task(
            "engine_resume_graph_background",
            args=(req.thread_id, serialized_inputs, config, "Resuming after cancellation...", False)
        )

    return CancelHITLResponse(
        status="cancelled",
        thread_id=req.thread_id,
        request_id=pending_tool["id"] if pending_tool else None,
    )


@router.post("/webhook")
async def webhook_endpoint(req: WebhookRequest, bg_tasks: BackgroundTasks):
    """
    Entry point for External Events (Local BG Task).
    """
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
            # CRITICAL: Invalidate project cache to prevent stale path overwrite
            # Background: _setup_project_context() in background_agent.py calls
            # evocloud_manager.get_project_by_id() which uses 60s TTL cache.
            # Without invalidation, the cache may return old path and overwrite
            # the new_path we just set here, causing Agent to operate on wrong directory.
            evocloud_manager.invalidate_projects_cache()
            logger.info("[Webhook] Project cache invalidated due to project_switched event")

            thread_context_store.set_working_directory(tid, new_path)
            # Dispatch Indexing Task directly from here if needed

            repo_name = os.path.basename(new_path)

            service = IndexingService()
            repo = await service.get_or_create_repo(new_path, repo_name)
            await indexing_manager.start_watching(new_path, repo.id)
            return WebhookResponse(status="switched", thread_id=tid)

    # Use Unified Dispatcher
    result = await dispatch_agent_run(
        thread_id=tid,
        message_content=messages[0].content if messages else "No content",
        project_id=DEFAULT_PROJECT_ID,  # Default project (global mode)
        goal_prefix=f"[{req.source.capitalize()} Event] ",
    )

    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)

    bg_tasks.add_task(run_agent_background, tid, result.inputs)
    # if settings.EMBEDDED_MODE:
    #     bg_tasks.add_task(run_agent_background, tid, result.inputs)
    # else:
    #     run_agent_background_task.delay(tid, result.inputs)

    return WebhookResponse(status="accepted", thread_id=tid)
