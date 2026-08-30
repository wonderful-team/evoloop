"""Mock chat simulation scenarios.

Each scenario is an async function that publishes a scripted sequence of
events to the event bus to simulate a realistic agent execution flow.
"""

import asyncio

from app.api.routes.chat.mock_helpers import (
    publish_ai_tool_call,
    publish_tool_output,
    publish_tool_start,
)
from app.core.engine.message.category import MessageCategory
from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.handler import MessageHandler
from app.core.engine.message.publisher import MessagePublisher
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.constants import ActivityStatus
from app.core.monitoring.schemas import HumanRequestData
from app.models.schemas.events import QuotaExhaustedEvent, StatusEvent
from app.utils.id import gen_uuid_hex


async def _stream_thinking(thread_id: str, text: str):
    for char in text:
        await MessageHandler.stream_thinking(thread_id, char)
        await asyncio.sleep(0.01)


async def _stream_tokens(thread_id: str, text: str):
    for char in text:
        await MessageHandler.stream_token(thread_id, char)
        await asyncio.sleep(0.01)


async def _publish_final_message(
    thread_id: str,
    seq_num: int,
    content: str,
    thinking: str,
    run_id: str,
):
    publisher = MessagePublisher(thread_id)
    msg_block = MessageBlockFactory.from_event(
        thread_id=thread_id,
        sequence_number=seq_num,
        role="ai",
        content=content,
        thinking=thinking,
        category="ai_response",
        status="completed",
        run_id=run_id,
    )
    await publisher.publish(msg_block)
    await asyncio.sleep(0.5)


async def happy_path_scenario(thread_id: str):
    """Simulate a normal streaming chat: plan → tool → plan → tool → answer."""
    run_id = f"run-mock-{gen_uuid_hex()[:8]}"
    await activity_monitor.start_run(thread_id, main_goal="正常流式对话模拟", run_id=run_id)
    await asyncio.sleep(0.5)

    # Turn 1: list_dir
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="分析项目结构以确定 UI 组件位置...",
    )
    await asyncio.sleep(0.5)
    await _stream_thinking(
        thread_id,
        "根据用户提出的任务，我需要先扫描前端组件目录结构，寻找可用的 Button 组件。\n",
    )
    await publish_ai_tool_call(
        thread_id, 2, "list_dir",
        {"DirectoryPath": "frontend/src/components"}, "call_ld1", run_id,
    )
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: list_dir",
        task_status="正在读取 frontend/src/components 目录...",
    )
    await publish_tool_start(
        thread_id, 3, "list_dir", "call_ld1",
        {"DirectoryPath": "frontend/src/components"}, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id,
        "正在获取目录中的文件列表...",
        progress=50,
        status="running",
    )
    await asyncio.sleep(0.5)
    dir_output = "['Button.tsx', 'Header.tsx', 'Footer.tsx']"
    await publish_tool_output(
        thread_id, 3, "list_dir", "call_ld1",
        {"DirectoryPath": "frontend/src/components"}, dir_output, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id, "目录列表读取成功。", progress=100, status="success"
    )
    await asyncio.sleep(0.5)

    # Turn 2: read_file
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="找到 Button.tsx，准备读取文件内容...",
    )
    await asyncio.sleep(0.5)
    await _stream_thinking(
        thread_id,
        "我已找到 Button.tsx 文件。现在我将读取它的代码内容以了解目前的属性定义。\n",
    )
    await publish_ai_tool_call(
        thread_id, 4, "read_file",
        {"AbsolutePath": "frontend/src/components/Button.tsx"}, "call_rf1", run_id,
    )
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: read_file",
        task_status="正在读取 frontend/src/components/Button.tsx...",
    )
    await publish_tool_start(
        thread_id, 5, "read_file", "call_rf1",
        {"AbsolutePath": "frontend/src/components/Button.tsx"}, run_id,
    )
    await asyncio.sleep(0.5)
    file_content = (
        "export function Button({ label }: { label: string }) {\n"
        "  return <button className='btn'>{label}</button>;\n"
        "}"
    )
    await publish_tool_output(
        thread_id, 5, "read_file", "call_rf1",
        {"AbsolutePath": "frontend/src/components/Button.tsx"},
        file_content, run_id,
    )
    await asyncio.sleep(0.5)

    # Turn 3: replace_file_content
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="分析代码并执行修改...",
    )
    await asyncio.sleep(0.5)
    await _stream_thinking(
        thread_id,
        "Button 组件目前的属性只支持 label。我需要支持 onClick 属性，"
        "并添加对应的点击回调类型。我将使用 replace_file_content 替换它。\n",
    )
    await publish_ai_tool_call(
        thread_id, 6, "replace_file_content",
        {"TargetFile": "frontend/src/components/Button.tsx"}, "call_rfc1", run_id,
    )
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: replace_file_content",
        task_status="正在应用替换逻辑...",
    )
    await publish_tool_start(
        thread_id, 7, "replace_file_content", "call_rfc1",
        {"TargetFile": "frontend/src/components/Button.tsx"}, run_id,
    )
    await asyncio.sleep(0.5)
    await publish_tool_output(
        thread_id, 7, "replace_file_content", "call_rfc1",
        {"TargetFile": "frontend/src/components/Button.tsx"},
        "File contents replaced successfully.", run_id,
    )
    await asyncio.sleep(0.5)

    # Turn 4: run_command (build)
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="编译检查与构建校验...",
    )
    await asyncio.sleep(0.5)
    await _stream_thinking(
        thread_id,
        "文件修改已完成。我将运行编译命令 npm run build 确保类型无误且项目成功构建。\n",
    )
    await publish_ai_tool_call(
        thread_id, 8, "run_command",
        {"CommandLine": "npm run build"}, "call_rc1", run_id,
    )
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: run_command",
        task_status="正在执行 npm run build...",
    )
    await publish_tool_start(
        thread_id, 9, "run_command", "call_rc1",
        {"CommandLine": "npm run build"}, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id, "Building application bundles...", progress=75, status="running",
    )
    await asyncio.sleep(0.8)
    await publish_tool_output(
        thread_id, 9, "run_command", "call_rc1",
        {"CommandLine": "npm run build"},
        "vite v5.0.0 building...\nbuilt in 350ms.\n✓ 15 modules transformed.",
        run_id,
    )
    await MessageHandler.stream_progress(
        thread_id, "编译构建通过。", progress=100, status="success"
    )
    await asyncio.sleep(0.5)

    # Final answer
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="生成最终答复...",
    )
    await asyncio.sleep(0.5)
    answer_thinking = "我将向用户反馈 Button.tsx 文件的修改已完成，并且已通过 Vite 构建编译测试。\n"
    await _stream_thinking(thread_id, answer_thinking)
    answer_content = (
        "你好！我已为您完成了对 `Button.tsx` 的读取与重构，"
        "并成功执行了项目编译构建检验 (`npm run build`)，无类型冲突和构建错误。"
    )
    await _stream_tokens(thread_id, answer_content)
    await _publish_final_message(thread_id, 10, answer_content, answer_thinking, run_id)
    await activity_monitor.end_run(
        thread_id,
        status=ActivityStatus.DONE,
        final_outcome="完成代码修改与校验",
        run_id=run_id,
    )


async def hitl_scenario(thread_id: str):
    """Simulate a human-in-the-loop approval flow for production deployment."""
    run_id = f"run-mock-{gen_uuid_hex()[:8]}"
    await activity_monitor.start_run(
        thread_id, main_goal="安全审批拦截模拟", run_id=run_id
    )
    await asyncio.sleep(0.5)

    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Decision",
        task_status="评估生产环境上线环境...",
    )
    await asyncio.sleep(0.5)
    await _stream_thinking(thread_id, "检测到发布任务，我将运行生产环境上线部署脚本。\n")
    await publish_ai_tool_call(
        thread_id, 2, "run_command",
        {"CommandLine": "npm run deploy:production"}, "call_dep1", run_id,
    )
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: run_command",
        task_status="正在执行 npm run deploy:production...",
    )
    await publish_tool_start(
        thread_id, 3, "run_command", "call_dep1",
        {"CommandLine": "npm run deploy:production"}, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id,
        "正在建立 SSH 连接并同步打包文件...",
        progress=40,
        status="running",
    )
    await asyncio.sleep(0.8)

    # Safety interruption
    await MessageHandler.stream_progress(
        thread_id=thread_id,
        message="[安全拦截] 检测到高危写操作指令，部署至生产环境需要获得项目管理员授权审批。",
        progress=40,
        status="interrupted",
    )
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data=HumanRequestData(
            type="approval",
            prompt="检测到即将执行部署脚本，是否批准部署至生产环境？",
            payload={"context": "生产服务器：aws-prod-01, 目标版本：v2.1.0"},
            allow_cancel=True,
        ),
    )
    await asyncio.sleep(4.0)
    await activity_monitor.clear_human_request(thread_id)

    # Resume after approval
    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="EXECUTING",
        task_name="Worker: run_command",
        task_status="用户已批准部署，正在恢复运行部署命令...",
    )
    await publish_tool_start(
        thread_id, 3, "run_command", "call_dep1",
        {"CommandLine": "npm run deploy:production"}, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id,
        "SSH 连接已恢复，正在传输构建制品包...",
        progress=80,
        status="running",
    )
    await asyncio.sleep(1.0)
    deploy_output = (
        "Assets uploaded successfully.\n"
        "Running health checks on remote server aws-prod-01...\n"
        "Health check: PASSED (200 OK)"
    )
    await publish_tool_output(
        thread_id, 3, "run_command", "call_dep1",
        {"CommandLine": "npm run deploy:production"}, deploy_output, run_id,
    )
    await MessageHandler.stream_progress(
        thread_id, "生产发布成功！", progress=100, status="success"
    )
    await asyncio.sleep(0.5)

    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Decision",
        task_status="生成上线总结报告...",
    )
    await asyncio.sleep(0.5)
    answer_thinking = "部署已成功完成，现在生成用户可读的上线确认报告。\n"
    await _stream_thinking(thread_id, answer_thinking)
    answer_content = "项目已成功发布至生产环境 (`aws-prod-01`)！所有服务已在线并处于健康运行状态。"
    await _stream_tokens(thread_id, answer_content)
    await _publish_final_message(thread_id, 4, answer_content, answer_thinking, run_id)
    await activity_monitor.end_run(
        thread_id,
        status=ActivityStatus.DONE,
        final_outcome="完成生产环境部署",
        run_id=run_id,
    )


async def quota_exhausted_scenario(thread_id: str):
    """Simulate a quota exhaustion error during LLM call."""
    run_id = f"run-mock-{gen_uuid_hex()[:8]}"
    await activity_monitor.start_run(
        thread_id, main_goal="配额异常检测模拟", run_id=run_id
    )
    await asyncio.sleep(0.5)

    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Decision",
        task_status="正在调度推理模型...",
    )
    await asyncio.sleep(1.0)
    await _stream_thinking(thread_id, "正在尝试调用大语言模型进行方案制定...\n")
    await asyncio.sleep(0.5)

    publisher = MessagePublisher(thread_id)
    await publisher.publish(
        QuotaExhaustedEvent(
            thread_id=thread_id,
            title="配额已耗尽",
            message="您当前的 LLM 账户使用配额已用完，无法继续处理请求。",
            hint="请联系系统管理员添加配额，或在系统设置中更换您的 API 密钥。",
        )
    )
    await asyncio.sleep(0.5)

    error_content = (
        "**配额已耗尽**\n"
        "您当前的 LLM 账户使用配额已用完，无法继续处理请求。\n\n"
        "*Hint: 请联系系统管理员添加配额，或在系统设置中更换您的 API 密钥。*"
    )
    msg_block = MessageBlockFactory.from_event(
        thread_id=thread_id,
        sequence_number=3,
        role="ai",
        content=error_content,
        category=MessageCategory.ERROR_SYSTEM.value,
        status="failed",
        run_id=run_id,
    )
    await publisher.publish(msg_block)
    await asyncio.sleep(0.5)

    await publisher.publish(StatusEvent(thread_id=thread_id, status="error"))
    await asyncio.sleep(0.5)

    await activity_monitor.end_run(
        thread_id,
        status=ActivityStatus.QUOTA_EXHAUSTED,
        final_outcome="因配额耗尽中断执行",
        run_id=run_id,
    )


async def long_task_scenario(thread_id: str):
    """Simulate a long-running task with 12 tool calls (code search)."""
    run_id = f"run-mock-{gen_uuid_hex()[:8]}"
    await activity_monitor.start_run(
        thread_id,
        main_goal="长程深度代码搜索与分析任务模拟",
        run_id=run_id,
    )
    await asyncio.sleep(0.5)

    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Plan",
        task_status="制定代码分析计划...",
    )
    await asyncio.sleep(0.8)
    await _stream_thinking(
        thread_id,
        "用户要求进行一次全库深度的依赖树检索，我需要拆分成多个子任务，"
        "首先交由 Worker 逐个目录进行 `grep_search` 和 `read_file`。\n",
    )

    for i in range(1, 13):
        tool_name = "grep_search" if i % 2 != 0 else "read_file"
        tool_args = (
            {"Query": f"dependency_{i}"}
            if i % 2 != 0
            else {"AbsolutePath": f"src/module_{i}.ts"}
        )
        call_id = f"call_loop_{i}"
        seq_base = i * 2

        await _stream_thinking(
            thread_id, f"\n准备执行第 {i} 步检索，调用 {tool_name}...\n"
        )
        await publish_ai_tool_call(
            thread_id, seq_base, tool_name, tool_args, call_id, run_id
        )
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="EXECUTING",
            task_name=f"Worker: Code Search {i}",
            task_status=f"正在执行深度检索 ({i}/12)...",
        )
        await publish_tool_start(
            thread_id, seq_base + 1, tool_name, call_id, tool_args, run_id
        )
        await MessageHandler.stream_progress(
            thread_id,
            f"正在搜索模块 {i}...",
            progress=(i * 100 // 12),
            status="running",
        )
        await asyncio.sleep(0.6)
        tool_out = (
            f"Found matches for query in module_{i}.ts lines 10-25.\n"
            if i % 2 != 0
            else f"export const mod_{i} = require('lib_{i}');"
        )
        await publish_tool_output(
            thread_id, seq_base + 1, tool_name, call_id, tool_args, tool_out, run_id
        )
        await asyncio.sleep(0.4)

    await activity_monitor.update_agent_state(
        thread_id=thread_id,
        mode="PLANNING",
        task_name="Supervisor Decision",
        task_status="正在汇总检索结果...",
    )
    await asyncio.sleep(0.5)
    answer_thinking = "检索结束，总计调用了数十次工具。现在我将向用户汇报汇总结果。\n"
    await _stream_thinking(thread_id, answer_thinking)
    answer_content = (
        "经过对整个代码库的数十次深度检索与阅读，"
        "我已经梳理清楚了您所需要的复杂依赖关系树！\n"
        "您可以查看上方的检索过程记录。"
    )
    await _stream_tokens(thread_id, answer_content)
    await _publish_final_message(
        thread_id, 100, answer_content, answer_thinking, run_id
    )
    await activity_monitor.end_run(
        thread_id,
        status=ActivityStatus.DONE,
        final_outcome="完成全库深度搜索分析",
        run_id=run_id,
    )


SCENARIOS = {
    "happy_path": happy_path_scenario,
    "hitl": hitl_scenario,
    "quota_exhausted": quota_exhausted_scenario,
    "long_task": long_task_scenario,
}
