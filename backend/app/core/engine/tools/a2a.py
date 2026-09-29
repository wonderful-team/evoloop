"""
A2A (Agent-to-Agent) runtime helpers — unified under the `agent` tool (§4.3/§10.2.2).

远端委派 / 结果回传 / 设备发现全部收敛到 ``engine/tools/react_task.py`` 的
``agent`` 工具：
- ``agent(action='run', remote={'agent_id': ...})`` → 本模块 ``dispatch_a2a_task``
  （派发 + 挂起主循环等回调恢复）；
- ``agent(action='complete')`` → 本模块 ``complete_a2a_task``（远端 Worker 侧把
  结果回传给 Caller，替代原 ``complete_task`` 工具）；
- ``agent(action='list')`` / system prompt ``<available_agents>`` 索引 →
  本模块 ``list_available_agents``。
"""

import logging

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import AgentTask, AgentTaskResult, TaskAttachment
from app.core.hitl.constants import MESSAGE_CATEGORY_HITL_REQUEST
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


# ==========================================
# 1. Available-agent listing (internal, §4.3)
# ==========================================
async def list_available_agents() -> str:
    """
    Query the EvoCloud registry for all currently online Agent devices.

    Returned as text so it can be injected into the system prompt
    ``<available_agents>`` index (task 工具描述语义，§4.3).
    """
    try:
        devices = await evocloud_manager.api.get_devices()
        if devices and devices.get("code") == 0:
            data = devices.get("data") or {}
            devices_list = data.get("list") or data.get("devices") or []
            online_agents = []
            for dev in devices_list:
                dev_type = dev.get("device_type")
                dev_status = dev.get("status")
                if (
                    dev_type
                    and dev_type not in ("mobile", "unknown")
                    and dev_status == "online"
                ):
                    online_agents.append(
                        {
                            "device_key": dev.get("device_key"),
                            "device_name": dev.get("device_name"),
                            "device_type": dev.get("device_type"),
                            "description": dev.get("description") or "",
                        }
                    )
            return "\n".join(
                f"- {a['device_key']} ({a['device_name']}): {a['description']}"
                for a in online_agents
            ) or "（当前无在线远端 Agent 设备）"
        return str(devices)
    except Exception as e:
        logger.exception(f"[A2A] ListAgents failed: {e}")
        return f"Error querying online agents: {e}"


# ==========================================
# 2. A2A task dispatch (internal, §4.3 remote 模式)
# ==========================================
async def dispatch_a2a_task(
    target_device_key: str,
    instruction: str,
    attachments: list[str] | None = None,
    tool_call_id: str | None = None,
) -> str:
    """向远端设备委派任务，挂起当前主循环等 A2A 回调恢复（§4.3）。

    Returns:
        永不正常返回——成功派发后抛出 ``AgentA2AInterruptException`` 挂起执行，
        失败返回错误文本。
    """
    attachments = attachments or []
    ctx = ContextManager.current()
    if not ctx:
        return "Error: No active execution context."

    thread_id = ctx.thread_id
    project_id = ctx.project_id or DEFAULT_PROJECT_ID

    hop_count = 1
    root_thread_id = thread_id

    from app.core.environment.discovery import EnvironmentProbe

    caller_role = EnvironmentProbe.get_inferred_device_type()
    global_goal = instruction

    async with session_scope() as session:
        conv = await session.get(Conversation, thread_id)
        if conv:
            global_goal = conv.title or instruction
            if conv.root_thread_id:
                root_thread_id = conv.root_thread_id

            # Trace the parent chain to count hops
            curr = conv
            while curr and curr.parent_thread_id:
                hop_count += 1
                curr = await session.get(Conversation, curr.parent_thread_id)

    if hop_count > 3:
        return "Error: Maximum chain delegation depth (3 hops) exceeded to prevent infinite loops."

    task_id = f"task-{gen_uuid()[:8]}"

    task_attachments = []
    for path in attachments:
        try:
            logger.info(f"[A2A] Uploading attachment: {path}")
            up_res = await evocloud_manager.api.upload_file(path)
            task_attachments.append(
                TaskAttachment(
                    filename=up_res["filename"],
                    download_url=up_res["download_url"],
                    file_size=up_res["file_size"],
                    md5=up_res["md5"],
                )
            )
        except Exception as e:
            logger.exception(f"[A2A] Failed to upload attachment {path}: {e}")
            return f"Error uploading attachment {path}: {e}"

    caller_device_key = (
        evocloud_manager.link.device_key if evocloud_manager.link else "unknown-caller"
    )

    task_envelope = AgentTask(
        task_id=task_id,
        instruction=instruction,
        caller_role=caller_role,
        global_goal=global_goal,
        attachments=task_attachments,
        caller_device_key=caller_device_key,
        root_thread_id=root_thread_id,
        parent_thread_id=thread_id,
        hop_count=hop_count,
        max_hops=3,
    )

    cmd_data = {
        "action": "a2a_task",
        "content": task_envelope.model_dump(),
        "thread_id": task_id,
        "project_id": project_id,
    }

    try:
        await evocloud_manager.api.send_command_to_device(
            device_key=target_device_key, cmd_data=cmd_data
        )
        logger.info(
            f"[A2A] Dispatched A2A task {task_id} to device {target_device_key}"
        )
    except Exception as e:
        logger.exception(f"[A2A] Failed to dispatch task to gateway: {e}")
        return f"Error dispatching task: {e}"

    # 发布公开生命周期事件（前端"A2A 委派"面板）。
    from app.core.events.publishers import publish_a2a_lifecycle

    await publish_a2a_lifecycle(
        thread_id=thread_id,
        task_id=task_id,
        target_device_key=target_device_key,
        instruction=instruction,
        status="started",
    )

    tool_call_id = tool_call_id or f"call-{task_id}"

    from app.core.monitoring.activity import HumanRequestData, activity_monitor

    req_data = HumanRequestData(
        type="a2a_callback",
        prompt=f"Waiting for A2A subtask callback from device {target_device_key}...",
        allow_cancel=True,
        payload={"task_id": task_id, "target_device_key": target_device_key},
    )

    from app.core.engine.message.repository import MessageRepository

    repo = MessageRepository(thread_id, project_id=project_id, run_id=ctx.run_id)
    await repo.persist(
        role="system",
        content=f"Waiting for A2A subtask callback from device {target_device_key}...",
        category=MESSAGE_CATEGORY_HITL_REQUEST,
        tool_call_id=tool_call_id,
        tool_name="agent",
        is_visible=True,
    )

    await activity_monitor.set_human_request(thread_id, req_data)

    from app.core.exceptions import AgentA2AInterruptException

    raise AgentA2AInterruptException(
        request_id=task_id,
        message=f"A2A Task {task_id} dispatched to {target_device_key}. Pausing execution.",
    )


# ==========================================
# 3. A2A Worker 侧回传结果（内部函数，由 task 工具 complete 模式调用，§4.3）
# ==========================================
async def complete_a2a_task(
    status: str, summary: str, attachments: list[str] | None = None
) -> str:
    """
    Finish executing the current A2A subtask and send the result back to the Caller Agent.
    This is the ONLY valid way to finish a subtask. Calling this will close the current session.
    """
    attachments = attachments or []

    ctx = ContextManager.current()
    if not ctx:
        return "Error: No active execution context."

    thread_id = ctx.thread_id
    project_id = ctx.project_id or DEFAULT_PROJECT_ID

    parent_thread_id = None
    caller_device_key = None

    async with session_scope() as session:
        conv = await session.get(Conversation, thread_id)
        if conv:
            parent_thread_id = conv.parent_thread_id
            caller_device_key = conv.caller_device_key

    if not parent_thread_id or not caller_device_key:
        return "Error: This session is not an active A2A worker task. Cannot send callback."

    task_attachments = []
    for path in attachments:
        try:
            logger.info(f"[A2A] Uploading callback attachment: {path}")
            up_res = await evocloud_manager.api.upload_file(path)
            task_attachments.append(
                TaskAttachment(
                    filename=up_res["filename"],
                    download_url=up_res["download_url"],
                    file_size=up_res["file_size"],
                    md5=up_res["md5"],
                )
            )
        except Exception as e:
            logger.exception(f"[A2A] Failed to upload callback attachment {path}: {e}")
            return f"Error uploading attachment {path}: {e}"

    callback_payload = AgentTaskResult(
        task_id=thread_id, status=status, summary=summary, attachments=task_attachments
    )

    cmd_data = {
        "action": "a2a_callback",
        "content": callback_payload.model_dump(),
        "thread_id": parent_thread_id,
        "project_id": project_id,
    }

    try:
        await evocloud_manager.api.send_command_to_device(
            device_key=caller_device_key, cmd_data=cmd_data
        )
        logger.info(
            f"[A2A] Sent A2A callback result for task {thread_id} to device {caller_device_key}"
        )
    except Exception as e:
        logger.exception(f"[A2A] Failed to send callback to caller: {e}")
        return f"Error sending callback: {e}"

    from app.core.monitoring.activity import activity_monitor
    from app.core.monitoring.constants import ActivityStatus

    await activity_monitor.end_run(thread_id, status=ActivityStatus.DONE, final_outcome=summary)

    from app.core.exceptions import AgentCancelledException

    raise AgentCancelledException("Task completed successfully. Session closed.")
