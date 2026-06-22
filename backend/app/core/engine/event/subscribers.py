"""
Engine Event Subscribers
========================

Event subscribers for the engine module, handling WebSocket commands
and agent dispatch.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sqlalchemy import delete

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.events import system_bus
from app.core.identity import identity_service
from app.core.context import thread_context_store
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.event.schemas import ConversationDeletedEvent, WebSocketMessageReceivedEvent
from app.core.engine.event.types import ConversationEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import RemoteCommand, AgentTaskResult, AgentTask
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import session_scope
from app.models import (
    AgentActivity,
    Conversation,
    FileOperation,
    HumanRequest,
    Message,
    ThreadSequence,
)
from app.utils import render_template

logger = logging.getLogger(__name__)

# 引擎域仅处理以下核心指令，其余指令（如 project_switch）由各自域的订阅者认领
ENGINE_ACTIONS = {
    "chat", "chat_message", "stop", "retry", "rewind",
    "hitl_response", "hitl_cancel",
    "a2a_task", "a2a_callback"
}


@event_register()
class EngineCommandSubscriber:
    """
    处理来自 WebSocket 的远程命令（new_command）。

    职责：
    1. 订阅通用 WebSocket 消息事件，过滤 new_command
    2. 执行保障：semaphore、状态上报、超时控制
    3. 业务处理：HITL 响应、控制命令、普通消息调度
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "new_command":
            return

        raw_cmd = event.payload
        action = raw_cmd.get("action") or raw_cmd.get("type") or "chat_message"

        # Conversation metadata sync (rename, pin, delete) — no engine pipeline needed
        if action in ("conversation_update", "conversation_delete"):
            await self._handle_conversation_action(raw_cmd)
            return

        if action not in ENGINE_ACTIONS:
            return

        await self._execute_with_guardrails(event.payload)

    async def _handle_conversation_action(self, cmd_data: dict) -> None:
        """Handle conversation metadata sync from Mobile (rename, pin, delete)."""
        action = cmd_data.get("action")
        thread_id = cmd_data.get("thread_id")
        if not thread_id:
            logger.warning(f"[EngineCommand] {action} missing thread_id, skipping")
            return

        if action == "conversation_update":
            title = cmd_data.get("title")
            is_pinned = cmd_data.get("is_pinned")
            if title is None and is_pinned is None:
                logger.warning(f"[EngineCommand] conversation_update has no fields to update, skipping")
                return
            async with session_scope() as session:
                conv = await session.get(Conversation, thread_id)
                if not conv:
                    logger.warning(f"[EngineCommand] conversation_update: conversation {thread_id} not found, skipping")
                    return
                if title is not None:
                    conv.title = title
                if is_pinned is not None:
                    conv.is_pinned = bool(is_pinned)
            logger.info(f"[EngineCommand] conversation_update applied: thread_id={thread_id}, title={title}, is_pinned={is_pinned}")

        elif action == "conversation_delete":
            # Publish event — each domain subscriber cleans up its own data
            from app.core.engine.event.publishers import publish_conversation_deleted
            await publish_conversation_deleted(thread_id)

            # Delete the Conversation row itself (ORM cascade covers messages, plan, etc.)
            async with session_scope() as session:
                conv = await session.get(Conversation, thread_id)
                if conv:
                    await session.delete(conv)
            logger.info(f"[EngineCommand] conversation_delete applied: thread_id={thread_id}")

    async def _execute_with_guardrails(self, cmd_data: dict) -> None:
        """
        命令执行的完整保障链路。

        包括并发控制（semaphore）与超时处理。业务逻辑最终委托给 ``_handle_command()``。
        """
        link = evocloud_manager.link
        cmd_id = cmd_data.get("command_id")

        async def _run() -> None:
            if link is None:
                logger.error(f"[EngineCommand] No link available for command execution: cmd_id={cmd_id}")
                return

            async with link._command_semaphore:
                try:
                    cmd = RemoteCommand.model_validate(cmd_data)
                    await self._handle_command(cmd)
                    logger.info(f"[EngineCommand] Command execution SUCCESS: cmd_id={cmd_id}")
                except Exception as e:
                    logger.error(f"[EngineCommand] Command execution FAILED: cmd_id={cmd_id}, error={e}")

        try:
            await asyncio.wait_for(_run(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"[EngineCommand] Command execution TIMEOUT: cmd_id={cmd_id}")
            if link:
                await link._force_reconnect()

    async def _handle_command(self, command: RemoteCommand) -> None:
        action = command.get_action()

        # [Control Commands]
        if action == "stop":
            await self._handle_stop(command)
        elif action == "retry":
            await self._handle_retry(command)
        elif action == "rewind":
            await self._handle_rewind(command)
        # [HITL Inbound Logic]
        elif action == "hitl_response":
            await self._handle_hitl_response(command)
        elif action == "hitl_cancel":
            await self._handle_hitl_cancel(command)
        # [Normal Chat Message Logic]
        elif action in {"chat", "chat_message"}:
            await self._handle_chat_message(command)
        # [A2A Task & Callback Logic]
        elif action == "a2a_task":
            await self._handle_a2a_task(command)
        elif action == "a2a_callback":
            await self._handle_a2a_callback(command)
        else:
            logger.debug(f"[EngineCommand] Skipping action {action} in engine domain")

    async def _handle_hitl_response(self, command: RemoteCommand) -> None:
        thread_id = command.get("thread_id")
        payload = command.get_payload()
        response = payload.get("response")

        if not thread_id or response is None:
            logger.debug("[EngineCommand] HITL response missing thread_id or response, skipping")
            return

        logger.info(f"[EngineCommand] Processing HITL Response for thread {thread_id}")

        # Persist the response message so it appears in history
        from app.core.engine.dispatch import persist_user_message

        await persist_user_message(
            thread_id=thread_id,
            content=str(response),
            project_id=command.get("project_id"),
            command_id=command.get("command_id"),
        )

        # Resolve model: prefer existing session model, fallback to system default
        from app.core.context.manager import ContextManager
        from app.core.engine.background_agent import BackgroundAgentInputs

        loaded_ctx = await ContextManager.load(thread_id)
        model = loaded_ctx.active_model if loaded_ctx else None
        if not model:
            model = SystemConfigService.get_value("LLM_MODEL")

        inputs = BackgroundAgentInputs(
            hitl_resume_response=response,
            command_id=command.get("command_id"),
            model=model,
        )
        asyncio.create_task(run_agent_background(thread_id, inputs))

    async def _handle_hitl_cancel(self, command: RemoteCommand) -> None:
        """
        Handle HITL cancellation from Mobile.
        """
        thread_id = command.get("thread_id")
        if not thread_id:
            logger.warning("[EngineCommand] HITL cancel missing thread_id, skipping")
            return

        logger.info(f"[EngineCommand] Processing HITL Cancellation for thread {thread_id}")

        # [HITL Closure]: Clear human request from activity monitor
        from app.core.monitoring.activity import activity_monitor
        await activity_monitor.clear_human_request(thread_id)

        # Resolve model: prefer existing session model, fallback to system default
        from app.core.context.manager import ContextManager
        from app.core.engine.background_agent import BackgroundAgentInputs

        loaded_ctx = await ContextManager.load(thread_id)
        model = loaded_ctx.active_model if loaded_ctx else None
        if not model:
            model = SystemConfigService.get_value("LLM_MODEL")

        inputs = BackgroundAgentInputs(
            hitl_resume_response="CANCELLED",
            command_id=command.get("command_id"),
            model=model,
        )
        asyncio.create_task(run_agent_background(thread_id, inputs))

    async def _handle_chat_message(self, command: RemoteCommand) -> None:
        # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
        """Handle normal chat message from Mobile."""
        payload = command.get_payload()

        # EPv2: 使用标准化字段
        message = payload.get("message") or payload.get("content") or ""

        # Mobile 通过 payload.references 发送的消息引用
        references = payload.get("references") or []
        if not message and not references:
            logger.debug("[EngineCommand] Remote command has no message or references, skipping")
            return

        thread_id = command.get("thread_id")
        if not thread_id:
            logger.error("[EngineCommand] Remote command missing thread_id, rejecting")
            raise ValueError("thread_id is required in remote command")

        logger.info(
            f"[EngineCommand] Executing remote command on thread {thread_id}: "
            f"Length={len(message) if message else 0}, References={len(references)}"
        )

        # Resolve Project ID
        pid_from_payload = command.get("project_id")
        pid_from_context = thread_context_store.get_active_project("remote-default")
        if pid_from_payload is not None:
            project_id = pid_from_payload
        elif pid_from_context is not None:
            project_id = pid_from_context
        else:
            project_id = DEFAULT_PROJECT_ID

        client_message_id = payload.get("client_message_id")

        # Unified dispatch preparation (DB persistence, EvoCloud sync, model fallback)
        member_id = await identity_service.get_member_id() or 0

        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=message or "",
            project_id=project_id,
            references=references,
            command_id=command.get("command_id"),
            model=None,
            member_id=member_id,
            source="mobile",
            client_message_id=client_message_id,
        )

        if result.status == "failed":
            logger.error(f"[EngineCommand] Dispatch failed for remote command: {result.error}")
            raise RuntimeError(f"Agent dispatch failed: {result.error}")

        # Start agent in background
        asyncio.create_task(run_agent_background(thread_id, result.inputs))

    async def _handle_stop(self, command: RemoteCommand) -> None:
        """Handle stop command from Mobile."""
        thread_id = command.get("thread_id")
        if not thread_id:
            logger.warning("[EngineCommand] Stop command missing thread_id, skipping")
            return
        logger.info(f"[EngineCommand] Stopping run for thread {thread_id}")
        from app.core.monitoring.activity import activity_monitor
        await activity_monitor.stop_run(thread_id)

    async def _handle_retry(self, command: RemoteCommand) -> None:
        """Handle retry command from Mobile (rewind + re-dispatch)."""
        await self._handle_retry_or_rewind(command, should_redispatch=True)

    async def _handle_rewind(self, command: RemoteCommand) -> None:
        """Handle rewind command from Mobile (rewind only, no re-dispatch)."""
        await self._handle_retry_or_rewind(command, should_redispatch=False)

    async def _handle_retry_or_rewind(self, command: RemoteCommand, should_redispatch: bool) -> None:
        """Shared logic for retry and rewind commands."""
        thread_id = command.get("thread_id")
        if not thread_id:
            logger.warning("[EngineCommand] Retry/Rewind command missing thread_id, skipping")
            return

        payload = command.get_payload()
        message_id = payload.get("message_id")
        revert_files = payload.get("revert_files", True)
        action = "retry" if should_redispatch else "rewind"

        logger.info(f"[EngineCommand] Processing {action} for thread {thread_id}, target={message_id}")

        from app.core.engine.rewind import RewindOrchestrator
        from app.core.context.manager import ContextManager

        async with session_scope() as session:
            if message_id:
                stmt = (
                    select(Message)
                    .options(selectinload(Message.references))
                    .where(Message.id == message_id)
                )
            else:
                stmt = (
                    select(Message)
                    .options(selectinload(Message.references))
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "human")
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )
            result = await session.execute(stmt)
            target_msg = result.scalar_one_or_none()

            if not target_msg:
                logger.error(f"[EngineCommand] No human message found for {action} thread {thread_id}")
                # Fallback: if message is missing locally, at least attempt to delete the target message from the cloud
                if message_id and payload.get("include_target", not should_redispatch):
                    from app.core.engine.rewind.event.publishers import publish_messages_cleanup
                    await publish_messages_cleanup(
                        thread_id=thread_id,
                        message_ids=[message_id],
                        delete_references=False,
                        target_sequence=0,
                        include_target=False,
                    )
                return

            references = None
            if target_msg.references:
                references = [
                    {
                        "type": ref.type,
                        "id": ref.target_id,
                        "target_id": ref.target_id,
                        "target_name": ref.target_name,
                        "meta_data": ref.meta_data,
                    }
                    for ref in target_msg.references
                ]

            retry_content = target_msg.content
            project_id = target_msg.project_id if target_msg.project_id is not None else DEFAULT_PROJECT_ID

        orchestrator = RewindOrchestrator(event_bus=system_bus)
        rewind_result = await orchestrator.perform_rewind(
            thread_id=thread_id,
            target_message_id=str(target_msg.id),
            include_target=payload.get("include_target", not should_redispatch),
            revert_files=revert_files,
            reset_state=should_redispatch,
            reason=action,
        )

        if rewind_result.status != "success":
            logger.error(f"[EngineCommand] {action} rewind failed: {rewind_result.errors}")
            return

        logger.info(
            f"[EngineCommand] {action} rewind completed: "
            f"{rewind_result.removed_message_count} messages removed"
        )

        if not should_redispatch:
            logger.info("[EngineCommand] Rewind done, no re-dispatch required")
            return

        # Retry: re-dispatch the message
        from app.core.context.manager import EvoContext
        ctx = EvoContext(thread_id=thread_id, project_id=project_id)
        ContextManager.set(ctx)

        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=retry_content,
            project_id=project_id,
            references=references,
            command_id=command.get("command_id"),
            model=None,
            is_retry=True,
            skip_message_persistence=True,
            goal_prefix="Retry: ",
            context=ctx,
        )

        if result.status == "failed":
            logger.error(f"[EngineCommand] Retry dispatch failed: {result.error}")
            return

        asyncio.create_task(run_agent_background(thread_id, result.inputs))

    async def _handle_a2a_task(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        logger.info(f"[A2A] Received A2A Task: {payload}")

        try:
            task = AgentTask.model_validate(payload)
        except Exception as e:
            logger.error(f"[A2A] Invalid AgentTask payload: {payload}, error={e}")
            return

        thread_id = task.task_id

        # Loop prevention check
        if task.hop_count > task.max_hops:
            logger.error(f"[A2A] Maximum hops exceeded: {task.hop_count} > {task.max_hops} for task {task.task_id}")
            await self._send_a2a_error(task, "Maximum chain delegation depth exceeded")
            return

        # Download attachments
        local_attachment_paths = []
        if task.attachments:
            download_dir = os.path.expanduser(os.path.join(settings.EVOLOOP_APP_DATA_DIR, "attachments", task.task_id))
            os.makedirs(download_dir, exist_ok=True)

            async with httpx.AsyncClient() as client:
                for att in task.attachments:
                    dest_path = os.path.join(download_dir, att.filename)
                    logger.info(f"[A2A] Downloading attachment {att.filename} from {att.download_url}...")
                    try:
                        async with client.stream("GET", att.download_url) as response:
                            response.raise_for_status()
                            with open(dest_path, "wb") as f:
                                async for chunk in response.aiter_bytes():
                                    f.write(chunk)

                        # Verify MD5
                        import hashlib
                        hash_md5 = hashlib.md5()
                        with open(dest_path, "rb") as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                hash_md5.update(chunk)
                        actual_md5 = hash_md5.hexdigest()

                        if actual_md5 != att.md5:
                            logger.error(f"[A2A] MD5 mismatch for {att.filename}. Expected: {att.md5}, Got: {actual_md5}")
                            await self._send_a2a_error(task, f"Attachment MD5 mismatch for {att.filename}")
                            return

                        local_attachment_paths.append(dest_path)
                    except Exception as ex:
                        logger.error(f"[A2A] Failed to download/verify attachment {att.filename}: {ex}")
                        await self._send_a2a_error(task, f"Failed to download attachment {att.filename}: {ex}")
                        return

        executor_device_key = evocloud_manager.link.device_key if evocloud_manager.link else "unknown-worker"
        executor_device_name = settings.EVOCLOUD_DEVICE_NAME

        project_id = command.get("project_id") or DEFAULT_PROJECT_ID
        from app.infrastructure.database.sql.database import session_scope
        async with session_scope() as session:
            conv = await session.get(Conversation, thread_id)
            if not conv:
                conv = Conversation(
                    id=thread_id,
                    project_id=project_id,
                    title=f"A2A: {task.instruction[:30]}",
                    root_thread_id=task.root_thread_id,
                    parent_thread_id=task.parent_thread_id,
                    caller_device_key=task.caller_device_key,
                    executor_device_key=executor_device_key,
                    executor_device_name=executor_device_name,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(conv)

        # Inject System Prompt Context
        system_content = render_template(
            "core/engine/a2a_system.prompt.j2",
            caller_device_key=task.caller_device_key,
            caller_role=task.caller_role,
            global_goal=task.global_goal,
            instruction=task.instruction,
            local_attachment_paths=local_attachment_paths,
        )

        from app.core.engine.message.repository import MessageRepository
        repo = MessageRepository(thread_id, project_id=project_id)
        await repo.persist(
            role="system",
            content=system_content,
            category="internal_system",
            is_visible=True,
        )

        # Dispatch Agent Run
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=task.instruction,
            project_id=project_id,
            command_id=command.get("command_id"),
            model=None,
            metadata={
                "task_type": "a2a_task",
                "task_id": task.task_id,
                "caller_device_key": task.caller_device_key,
                "root_thread_id": task.root_thread_id,
                "parent_thread_id": task.parent_thread_id,
            }
        )

        if result.status == "failed":
            logger.error(f"[A2A] Dispatch failed for A2A task: {result.error}")
            await self._send_a2a_error(task, f"Agent dispatch failed: {result.error}")
            return

        asyncio.create_task(run_agent_background(thread_id, result.inputs))

    async def _send_a2a_error(self, task: Any, error_msg: str) -> None:
        from app.core.evocloud.manager import evocloud_manager

        callback_payload = AgentTaskResult(
            task_id=task.task_id,
            status="failed",
            error=error_msg,
            summary=f"Error: {error_msg}"
        )

        cmd_data = {
            "action": "a2a_callback",
            "payload": callback_payload.model_dump(),
            "thread_id": task.parent_thread_id,
        }

        try:
            await evocloud_manager.api.send_command_to_device(
                device_key=task.caller_device_key,
                cmd_data=cmd_data
            )
            logger.info(f"[A2A] Error callback sent to caller {task.caller_device_key} for task {task.task_id}")
        except Exception as e:
            logger.error(f"[A2A] Failed to send error callback to caller {task.caller_device_key}: {e}")

    async def _handle_a2a_callback(self, command: RemoteCommand) -> None:
        payload = command.get_payload()
        logger.info(f"[A2A] Received A2A Callback: {payload}")

        try:
            result = AgentTaskResult.model_validate(payload)
        except Exception as e:
            logger.error(f"[A2A] Invalid AgentTaskResult: {payload}, error={e}")
            return

        task_id = result.task_id
        caller_thread_id = command.get("thread_id")

        if not caller_thread_id:
            from app.infrastructure.database.sql.database import session_scope
            from app.models import Conversation
            async with session_scope() as session:
                conv = await session.get(Conversation, task_id)
                if conv:
                    caller_thread_id = conv.parent_thread_id

        if not caller_thread_id:
            logger.error(f"[A2A] Caller thread_id not found for task_id: {task_id}")
            return

        # Clear human request on Caller thread
        from app.core.monitoring.activity import activity_monitor
        await activity_monitor.clear_human_request(caller_thread_id)

        # Build response payload
        result_content = json.dumps(result.model_dump(), ensure_ascii=False)

        # Close the pending tool call message
        tool_call_id = None
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == caller_thread_id)
                .where(Message.role == "ai")
                .order_by(Message.sequence_number.desc())
                .limit(5)
            )
            res = await session.execute(stmt)
            messages = res.scalars().all()
            for msg in messages:
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.get("name") in ("SendAgentTaskTool", "send_agent_task"):
                            tool_call_id = tc.get("id")
                            break
                if tool_call_id:
                    break

        if tool_call_id:
            from app.core.hitl.orchestrator import close_hitl_interaction
            await close_hitl_interaction(caller_thread_id, tool_call_id, "completed")
        else:
            logger.warning(f"[A2A] Could not find matching pending tool call for task_id {task_id}")

        # Resume Caller Agent
        from app.core.context.manager import ContextManager
        from app.core.engine.background_agent import BackgroundAgentInputs

        loaded_ctx = await ContextManager.load(caller_thread_id)
        model = loaded_ctx.active_model if loaded_ctx else None
        if not model:
            model = SystemConfigService.get_value("LLM_MODEL")
        if not model:
            # Fallback: 从 Gateway 拉取第一个可用的平台 LLM 模型
            # 适用于进程重启后 ContextManager 丢失、且本地 DB 未配置 LLM_MODEL 的情况
            try:
                from app.infrastructure.llm.platform_service import llm_platform_service
                platform_models = await llm_platform_service.fetch_platform_models()
                llm_models = [m for m in platform_models if m.model_type == "llm"]
                if llm_models:
                    model = llm_models[0].model_id
                    logger.info(f"[A2A] Model resolved from platform: {model}")
            except Exception as e:
                logger.warning(f"[A2A] Failed to fetch platform models for fallback: {e}")

        if not model:
            logger.error(f"[A2A] Cannot resume Caller thread {caller_thread_id}: no model available")
            return

        inputs = BackgroundAgentInputs(
            hitl_resume_response=result_content,
            model=model,
        )
        logger.info(f"[A2A] Resuming Caller Agent on thread {caller_thread_id}")
        asyncio.create_task(run_agent_background(caller_thread_id, inputs))


@event_register()
class EngineConversationCleanup:
    """
    Cleans up engine-owned data when a conversation is deleted.
    """

    @event_subscribe(ConversationEventType.CONVERSATION_DELETED)
    async def on_conversation_deleted(self, event: ConversationDeletedEvent) -> None:
        thread_id = event.thread_id
        logger.info(f"[EngineCleanup] Cleaning up engine data for thread {thread_id}")

        # 1. Delete checkpoints
        checkpointer = db_resource_manager.checkpointer
        if checkpointer:
            try:
                await checkpointer.adelete_thread(thread_id)
            except Exception as e:
                logger.warning(f"[EngineCleanup] Checkpoint deletion failed: {e}")

        # 2. Delete engine-owned DB records
        async with session_scope() as session:
            await session.execute(delete(AgentActivity).where(AgentActivity.thread_id == thread_id))
            await session.execute(delete(ThreadSequence).where(ThreadSequence.thread_id == thread_id))
            await session.execute(delete(HumanRequest).where(HumanRequest.thread_id == thread_id))
            await session.execute(delete(FileOperation).where(FileOperation.thread_id == thread_id))

        logger.info(f"[EngineCleanup] Engine cleanup done for thread {thread_id}")
