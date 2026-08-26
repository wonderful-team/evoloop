"""
Engine Event Subscribers
========================

Event subscribers for the engine module, handling WebSocket commands
and agent dispatch.

Heavy command logic (memory, A2A) is delegated to dedicated handler modules
in ``app.core.engine.event.handlers``.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.constants import DEFAULT_PROJECT_ID
from app.core.channel.input.mobile_input import mobile_input
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.event import ConversationEventType
from app.core.engine.event.handlers import A2ACommandHandler, MemoryCommandHandler
from app.core.engine.event.schemas import (
    ConversationDeletedEvent,
    WebSocketMessageReceivedEvent,
)
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.bridge.conversation_sync import get_conversation_sync_manager
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import RemoteCommand
from app.core.hitl.types import HITLDecision
from app.core.identity import identity_service
from app.core.schemas.canonical import MessageType
from app.infrastructure.database import session_scope
from app.models import (
    AgentActivity,
    Conversation,
    FileOperation,
    HumanRequest,
    Message,
    ThreadSequence,
)

logger = logging.getLogger(__name__)

# 引擎域仅处理以下核心指令，其余指令（如 project_switch）由各自域的订阅者认领
ENGINE_ACTIONS = {
    "chat",
    "stop",
    "retry",
    "rewind",
    "hitl_response",
    "hitl_cancel",
    "memory_add",
    "memory_update",
    "memory_delete",
    "a2a_task",
    "a2a_callback",
}

# 信封类型 → 引擎动作。command.relay 的动作在 body.action 中；其余类型
# 由信封类型本身决定（对应 schemas/types/ 下各自的独立 envelope 类型）。
_MSG_TYPE_ACTION: dict[str, str] = {
    "command.retry": "retry",
    "command.rewind": "rewind",
    "command.stop": "stop",
    "hitl.response": "hitl_response",
    "hitl.cancel": "hitl_cancel",
}


@event_register()
class EngineCommandSubscriber:
    """
    处理来自 WebSocket 的远程命令（command.relay / command.stop / hitl.response 等）。

    职责：
    1. 订阅通用 WebSocket 消息事件，过滤引擎域支持的信封类型
    2. 执行保障：semaphore、状态上报、超时控制
    3. 业务处理：HITL 响应、控制命令、普通消息调度
    4. 委托 Memory / A2A 命令到专用 handler
    """

    def __init__(self) -> None:
        self._memory_handler = MemoryCommandHandler()
        self._a2a_handler = A2ACommandHandler()

    @event_subscribe(SystemEventType.WEBSOCKET_MESSAGE_RECEIVED)
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type == "command.relay":
            pass
        elif event.msg_type not in _MSG_TYPE_ACTION:
            return

        raw_cmd = dict(event.payload or {})
        # command.relay carries the action in body.action; the other envelope
        # types encode the action in the type itself (schemas/types/*.json).
        if event.msg_type == "command.relay":
            action = raw_cmd.get("action") or "chat"
        else:
            action = _MSG_TYPE_ACTION[event.msg_type]
            # hitl.response body.action is the schema enum confirm|choice|text;
            # preserve it and stamp the engine-domain action for dispatch.
            if event.msg_type == "hitl.response" and raw_cmd.get("action"):
                raw_cmd["response_action"] = raw_cmd["action"]
            raw_cmd["action"] = action

        # Normalize payload so downstream handlers can read message_id/revert_files
        if action in ("retry", "rewind") and "content" not in raw_cmd:
            raw_cmd["content"] = {
                "message_id": raw_cmd.get("message_id"),
                "revert_files": raw_cmd.get("revert_files", True),
            }

        # Conversation metadata sync (rename, pin, delete) — no engine pipeline needed
        if action in ("conversation_update", "conversation_delete"):
            await self._handle_conversation_action(raw_cmd)
            return

        if action not in ENGINE_ACTIONS:
            return

        await self._execute_with_guardrails(raw_cmd)

    async def _handle_conversation_action(self, cmd_data: dict) -> None:
        """Handle conversation metadata sync from Mobile (rename, pin, delete)."""
        action = cmd_data.get("action")
        thread_id = cmd_data.get("thread_id")
        if not thread_id:
            logger.warning(f"[EngineCommand] {action} missing thread_id, skipping")
            return

        async def _trigger_sync() -> None:
            try:
                manager = get_conversation_sync_manager(
                    evocloud_manager.api, evocloud_manager.link.device_key
                )
                await manager.incremental_sync()
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[EngineCommand] Failed to trigger conversation sync: {e}", exc_info=True)

        if action == "conversation_update":
            # Mobile sends metadata inside the payload/content field.
            payload = cmd_data.get("content") or {}
            if isinstance(payload, str):
                payload = {"title": payload}
            title = payload.get("title")
            is_pinned = payload.get("is_pinned")
            if title is None and is_pinned is None:
                logger.warning(
                    "[EngineCommand] conversation_update has no fields to update, "
                    "skipping"
                )
                return
            async with session_scope() as session:
                conv = await session.get(Conversation, thread_id)
                if not conv:
                    logger.warning(
                        f"[EngineCommand] conversation_update: conversation "
                        f"{thread_id} not found, skipping"
                    )
                    return
                if title is not None:
                    conv.title = title
                if is_pinned is not None:
                    conv.is_pinned = bool(is_pinned)
                conv.sync_status = "pending"
                conv.updated_at = datetime.now(timezone.utc)
            logger.info(
                f"[EngineCommand] conversation_update applied: "
                f"thread_id={thread_id}, title={title}, is_pinned={is_pinned}"
            )
            await _trigger_sync()

        elif action == "conversation_delete":
            # Publish event — each domain subscriber cleans up its own data
            from app.core.engine.event.publishers import publish_conversation_deleted

            await publish_conversation_deleted(thread_id)

            # Sync deletion to MC before removing the local row.
            try:
                await evocloud_manager.api.sync_delete_conversation(
                    evocloud_manager.link.device_key, thread_id
                )
                logger.info(
                    f"[EngineCommand] conversation_delete synced to MC: thread_id={thread_id}"
                )
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(
                    f"[EngineCommand] Failed to sync conversation_delete to MC: thread_id={thread_id}, error={e}"
                , exc_info=True)

            # Delete the Conversation row itself (ORM cascade covers messages, plan, etc.)
            async with session_scope() as session:
                conv = await session.get(Conversation, thread_id)
                if conv:
                    await session.delete(conv)
            logger.info(
                f"[EngineCommand] conversation_delete applied: thread_id={thread_id}"
            )

    async def _execute_with_guardrails(self, cmd_data: dict) -> None:
        """
        命令执行的完整保障链路。

        包括并发控制（semaphore）与超时处理。业务逻辑最终委托给 ``_handle_command()``。
        """
        link = evocloud_manager.link
        cmd_id = cmd_data.get("command_id")

        async def _run() -> None:
            if link is None:
                logger.error(
                    "[EngineCommand] No link available for command execution: "
                    f"cmd_id={cmd_id}"
                )
                return

            async with link._command_semaphore:
                try:
                    command = RemoteCommand.model_validate(cmd_data)
                    await self._handle_command(command)
                    logger.info(f"[EngineCommand] Command execution SUCCESS: cmd_id={cmd_id}")
                    await self._send_ack(cmd_id, "completed", thread_id=command.thread_id)
                except Exception as e:
                    logger.error("[EngineCommand] Command execution FAILED: cmd_id={cmd_id}, error={e}")
                    await self._send_ack(
                        cmd_id,
                        "failed",
                        error=str(e),
                        thread_id=cmd_data.get("thread_id"),
                    )

        try:
            await asyncio.wait_for(_run(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.exception(f"[EngineCommand] Command execution TIMEOUT: cmd_id={cmd_id}")
            if link:
                await link._force_reconnect()

    async def _send_ack(
        self,
        cmd_id: int,
        status: str,
        error: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        """发送 command.ack 给 Gateway (received 已由 link-layer 发送，这里发 final 状态)。"""
        from app.core.channel import channel_registry

        ch = channel_registry.get("mobile")
        if ch is None:
            return

        body = {"command_id": cmd_id, "status": status}
        if thread_id:
            body["thread_id"] = thread_id
        if error:
            body["error"] = error
        await ch.send_envelope(
            env_type=MessageType.COMMAND_ACK,
            body=body,
        )
        logger.info(
            f"[EngineCommand] command.ack sent: cmd_id={cmd_id}, status={status}"
        )

    async def _handle_command(self, command: RemoteCommand) -> None:
        action = command.get_action()

        # [Control Commands]
        if action == "stop":
            await self._handle_stop(command)
        elif action == "retry":
            await self._handle_retry(command)
        elif action == "rewind":
            await self._handle_rewind(command)
        # [Memory Commands]
        elif action in ("memory_add", "memory_update", "memory_delete"):
            await self._memory_handler.handle(action, command)
        # [HITL Inbound Logic]
        elif action == "hitl_response":
            await self._handle_hitl_response(command)
        elif action == "hitl_cancel":
            await self._handle_hitl_cancel(command)
        # [Normal Chat Message Logic]
        elif action == "chat":
            await self._handle_chat_message(command)
        # [A2A Task & Callback Logic]
        elif action in ("a2a_task", "a2a_callback"):
            await self._a2a_handler.handle(action, command)
        else:
            logger.warning(
                "[EngineCommand] Skipping action %r in engine domain — no subscriber "
                "handles it, message silently dropped",
                action,
            )

    async def _handle_hitl_response(self, command: RemoteCommand) -> None:
        thread_id = command.get("thread_id")
        payload = command.get_payload()
        # schema hitl.response body: {request_id, action: confirm|choice|text,
        # value}.  value 即用户答复。旧版 command.relay 形态把答复放在
        # content.response。
        response = command.get("value") or payload.get("value") or payload.get("response")
        response_action = command.get("response_action") or payload.get("action")

        if not thread_id or response is None:
            logger.debug(
                "[EngineCommand] HITL response missing thread_id or response, skipping"
            )
            return

        logger.info(
            "[EngineCommand] Processing HITL Response for thread %s (action=%s)",
            thread_id,
            response_action or "unknown",
        )

        # Persist the response message so it appears in history
        from app.core.engine.dispatch import persist_user_message

        await persist_user_message(
            thread_id=thread_id,
            content=str(response),
            project_id=command.get("project_id"),
        )

        # 会话模式：统一走 session_manager.submit（is_resume）—— 有活会话注入
        # gate 恢复，无活会话创建并启动；不再回落到 run_agent_background。
        from app.core.session.manager import session_manager

        await session_manager.submit(thread_id, response, is_resume=True)

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

        # 会话模式：统一走 session_manager.submit（is_resume + is_cancel）
        from app.core.session.manager import session_manager

        await session_manager.submit(
            thread_id,
            "CANCELLED",
            is_resume=True,
            is_cancel=True,
        )

    async def _handle_chat_message(self, command: RemoteCommand) -> None:
        #         Mobile sends chat content inside the command.relay body's `content` field,
        #  @schemas/types/command.relay.json: content = { text: "..." }
        #  We extract the payload here (transport-specific), then pass to mobile_input.
        payload = command.get_payload()

        thread_id = command.get("thread_id")
        if not thread_id:
            logger.error("[EngineCommand] Remote command missing thread_id, rejecting")
            raise ValueError("thread_id is required in remote command")

        member_id = await identity_service.get_member_id() or 0

        # 移动端与 web 文字链路对齐：跳过 L0、先走 L1 领域分类再进 Agent。
        # 统一经 dispatch_user_message → command_router.resolve(skip_l0=True)。
        from app.constants import DEFAULT_PROJECT_ID
        from app.core.context import EvoContext
        from app.core.routing.dispatch_handler import dispatch_user_message
        from app.core.routing.thread_locks import route_lock_scope
        from app.core.state import shared_state
        from app.utils.id import gen_uuid

        raw_payload = payload if isinstance(payload, dict) else {"text": str(payload)}
        req_pid = int(raw_payload.get("project_id", 0))
        if req_pid:
            await shared_state.set_active_project_id(req_pid)
            pid = req_pid
        else:
            pid = await shared_state.get_active_project_id() or DEFAULT_PROJECT_ID

        ctx = EvoContext(
            request_id=command.get("message_id") or gen_uuid(),
            thread_id=thread_id,
            project_id=pid,
            member_id=member_id,
            command_id=command.get("command_id"),
        )

        raw = {
            **raw_payload,
            "thread_id": thread_id,
            "project_id": pid,
            "command_id": command.get("command_id"),
            "message_id": command.get("message_id"),
        }

        async with route_lock_scope(thread_id, ctx):
            outcome = await dispatch_user_message(
                raw,
                source="mobile",
                input_channel=mobile_input,
                thread_id=thread_id,
                project_id=pid,
                member_id=member_id,
                context=ctx,
            )

            if outcome.msg is None:
                return

            if outcome.handled:
                # skip_l0 下移动端不会命中 L0 宏/导航/本地动作，此处防御性兜底。
                logger.info(
                    "[EngineCommand] mobile L0 handled (unexpected): %s",
                    outcome.local_response,
                )
                return

            inputs = outcome.inputs
            if inputs is None or inputs.status == "failed":
                if inputs is not None:
                    logger.error(f"[EngineCommand] Dispatch failed: {inputs.error}")
                    raise RuntimeError(f"Agent dispatch failed: {inputs.error}")
                return

            # 会话模式：统一走 session_manager.submit —— 有活会话注入，
            # 无活会话创建并启动；不再回落到 run_agent_background。
            from app.core.session.manager import session_manager

            await session_manager.submit(thread_id, inputs.inputs)

    async def _handle_stop(self, command: RemoteCommand) -> None:
        """Handle stop command from Mobile."""
        thread_id = command.get("thread_id")
        if not thread_id:
            logger.warning("[EngineCommand] Stop command missing thread_id, skipping")
            return
        logger.info(f"[EngineCommand] Stopping run for thread {thread_id}")
        # 会话模式：统一走 session_manager.stop_agent（有会话 → session.stop；
        # 无会话 → stop_run + cancel_worker 双兜底）
        from app.core.session.manager import session_manager

        await session_manager.stop_agent(thread_id, "mobile_stop")

    async def _handle_retry(self, command: RemoteCommand) -> None:
        """Handle retry command from Mobile (rewind + re-dispatch)."""
        await self._handle_retry_or_rewind(command, should_redispatch=True)

    async def _handle_rewind(self, command: RemoteCommand) -> None:
        """Handle rewind command from Mobile (rewind only, no re-dispatch)."""
        await self._handle_retry_or_rewind(command, should_redispatch=False)

    async def _handle_retry_or_rewind(
        self, command: RemoteCommand, should_redispatch: bool
    ) -> None:
        """Shared logic for retry and rewind commands."""
        thread_id = command.get("thread_id")
        if not thread_id:
            logger.warning("[EngineCommand] Retry/Rewind command missing thread_id, skipping")
            return

        payload = command.get_payload()
        message_id = command.get("message_id")
        revert_files = payload.get("revert_files", True)
        action = "retry" if should_redispatch else "rewind"

        logger.info(f"[EngineCommand] Processing {action} for thread {thread_id}, target={message_id}")

        from app.core.context.manager import ContextManager
        from app.core.engine.rewind import perform_rewind

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
                    from app.core.engine.rewind import publish_messages_cleanup

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
            project_id = (
                target_msg.project_id
                if target_msg.project_id is not None
                else DEFAULT_PROJECT_ID
            )

        rewind_result = await perform_rewind(
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

        logger.info(f"[EngineCommand] {action} rewind completed: {rewind_result.removed_message_count} messages removed")

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
            context=ctx,
            metadata={"goal_prefix": "Retry: "},
        )

        if result.status == "failed":
            logger.error(f"[EngineCommand] Retry dispatch failed: {result.error}")
            return

        # 会话模式：统一走 session_manager.submit —— 有活会话注入（会话重建 state
        # 反映 rewind 后的 DB）；无活会话创建并启动，不再回落到 run_agent_background。
        from app.core.session.manager import session_manager

        await session_manager.submit(thread_id, result.inputs)


@event_register()
class EngineConversationCleanup:
    """
    Cleans up engine-owned data when a conversation is deleted.
    """

    @event_subscribe(ConversationEventType.CONVERSATION_DELETED)
    async def on_conversation_deleted(self, event: ConversationDeletedEvent) -> None:
        thread_id = event.thread_id
        logger.info(f"[EngineCleanup] Cleaning up engine data for thread {thread_id}")

        # 1. Delete engine-owned DB records
        async with session_scope() as session:
            await session.execute(delete(AgentActivity).where(AgentActivity.thread_id == thread_id))
            await session.execute(delete(ThreadSequence).where(ThreadSequence.thread_id == thread_id))
            await session.execute(delete(HumanRequest).where(HumanRequest.thread_id == thread_id))
            await session.execute(delete(FileOperation).where(FileOperation.thread_id == thread_id))

        logger.info(f"[EngineCleanup] Engine cleanup done for thread {thread_id}")
