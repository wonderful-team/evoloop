"""
Engine Event Subscribers
========================

Event subscribers for the engine module, handling WebSocket commands
and agent dispatch.
"""

import asyncio
import logging

from app.core.context import thread_context_store
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.event.schemas import WebSocketMessageReceivedEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import RemoteCommand

logger = logging.getLogger(__name__)


@event_register()
class EngineCommandHandler:
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
        await self._execute_with_guardrails(event.payload)

    async def _execute_with_guardrails(self, cmd_data: dict) -> None:
        """
        命令执行的完整保障链路。

        包括并发控制（semaphore）、状态上报（Running/Completed/Failed）、
        超时处理。业务逻辑最终委托给 ``_handle_command()``。
        """
        link = evocloud_manager.link
        api = evocloud_manager.api if link else None
        cmd_id = cmd_data.get("command_id")

        async def _run() -> None:
            if link is None:
                logger.error(f"[EngineCommand] No link available for command execution: cmd_id={cmd_id}")
                return

            async with link._command_semaphore:
                if api:
                    await api.update_command_status(cmd_id, 2)  # Running
                try:
                    cmd = RemoteCommand.model_validate(cmd_data)
                    await self._handle_command(cmd)
                    if api:
                        await api.update_command_status(cmd_id, 3)  # Completed
                    logger.info(f"[EngineCommand] Command execution SUCCESS: cmd_id={cmd_id}")
                except Exception as e:
                    logger.error(f"[EngineCommand] Command execution FAILED: cmd_id={cmd_id}, error={e}")
                    if api:
                        await api.update_command_status(cmd_id, 4, str(e))  # Failed

        try:
            await asyncio.wait_for(_run(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"[EngineCommand] Command execution TIMEOUT: cmd_id={cmd_id}")
            if api:
                try:
                    await api.update_command_status(cmd_id, 4, "execution timeout")
                except Exception as e:
                    logger.error(f"[EngineCommand] Failed to update timeout status: {e}")
            if link:
                await link._force_reconnect()

    async def _handle_command(self, command: RemoteCommand) -> None:
        cmd_type = command.get("type", "chat_message")

        # [Control Commands]
        if cmd_type == "stop":
            await self._handle_stop(command)
            return
        elif cmd_type == "retry":
            await self._handle_retry(command)
            return
        elif cmd_type == "rewind":
            await self._handle_rewind(command)
            return

        # [HITL Inbound Logic]
        if cmd_type == "hitl_response":
            await self._handle_hitl_response(command)
            return

        # [Normal Chat Message Logic]
        await self._handle_chat_message(command)

    async def _handle_hitl_response(self, command: RemoteCommand) -> None:
        thread_id = command.get("thread_id")
        response = (command.get("content") or {}).get("response")

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
        from app.infrastructure.config.service import SystemConfigService

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

    async def _handle_chat_message(self, command: RemoteCommand) -> None:
        # Support both nested 'content' (legacy/cloud) and flat 'message' (mobile/local) structures
        content_obj = command.get("content") or {}
        params_obj = content_obj.get("params", {})

        message = (
            command.get("message")
            or content_obj.get("text")
            or content_obj.get("message")
            or params_obj.get("message")
        )

        attachments = (
            command.get("attachments")
            or content_obj.get("attachments")
            or params_obj.get("attachments")
            or []
        )

        # Mobile 通过 content.references 发送的消息引用（引用历史消息 / 文件等）
        # 将其合并到 attachments 中，由 reference_service.process_references() 统一处理
        references = content_obj.get("references") or []
        if references:
            attachments = list(attachments) + list(references)

        if not message and not attachments:
            logger.debug("[EngineCommand] Remote command has no message or attachments, skipping")
            return

        thread_id = command.get("thread_id")
        if not thread_id:
            logger.error("[EngineCommand] Remote command missing thread_id, rejecting")
            raise ValueError("thread_id is required in remote command")

        logger.info(
            f"[EngineCommand] Executing remote command on thread {thread_id}: "
            f"Length={len(message) if message else 0}, Attachments={len(attachments)}"
        )

        # Resolve Project ID
        pid_from_payload = command.get("project_id")
        pid_from_context = thread_context_store.get_active_project("remote-default")
        project_id = pid_from_payload or pid_from_context or 1

        # Unified dispatch preparation (DB persistence, EvoCloud sync, model fallback)
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=message or "",
            project_id=project_id,
            attachments=attachments,
            command_id=command.get("command_id"),
            model=None,  # Remote commands don't carry model selection; fallback to default
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

        content_obj = command.get("content") or {}
        message_id = content_obj.get("message_id")
        revert_files = content_obj.get("revert_files", True)
        action = "retry" if should_redispatch else "rewind"

        logger.info(f"[EngineCommand] Processing {action} for thread {thread_id}, target={message_id}")

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message
        from app.core.engine.rewind import RewindOrchestrator
        from app.core.engine.rewind.exceptions import RewindError
        from app.core.events import system_bus
        from app.core.context.manager import ContextManager

        async with session_scope() as session:
            if message_id:
                stmt = (
                    select(Message)
                    .options(selectinload(Message.references))
                    .where(Message.id == int(message_id))
                )
            else:
                stmt = (
                    select(Message)
                    .options(selectinload(Message.references))
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "human")
                    .order_by(Message.id.desc())
                    .limit(1)
                )
            result = await session.execute(stmt)
            target_msg = result.scalar_one_or_none()

            if not target_msg:
                logger.error(f"[EngineCommand] No human message found for {action} thread {thread_id}")
                return

            attachments = None
            if target_msg.references:
                attachments = [
                    {
                        "type": ref.type,
                        "id": ref.target_id,
                        "name": ref.target_name,
                        "url": ref.target_id if ref.type in ("file", "image") else None,
                    }
                    for ref in target_msg.references
                ]

            retry_content = target_msg.content
            project_id = target_msg.project_id or 1

        try:
            orchestrator = RewindOrchestrator(event_bus=system_bus)
            rewind_result = await orchestrator.perform_rewind(
                thread_id=thread_id,
                target_message_id=str(target_msg.id),
                include_target=False,
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
        except RewindError as e:
            logger.error(f"[EngineCommand] {action} rewind failed: {e}")
            return

        if not should_redispatch:
            logger.info(f"[EngineCommand] Rewind done, no re-dispatch required")
            return

        # Retry: re-dispatch the message
        ctx = ContextManager.create_context(thread_id=thread_id, project_id=project_id)
        ContextManager.set(ctx)

        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=retry_content,
            project_id=project_id,
            attachments=attachments,
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
