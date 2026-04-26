"""
MessageHandler - 消息处理器

整合分类、持久化、推送策略的统一入口。
替代原来分散在各 callback 中的处理逻辑。
"""
import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import select, func

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.persistence import MessagePersistencePolicy
from app.core.engine.message.stream import MessageStreamPolicy
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.infrastructure.queue.factory import get_scheduler
from app.models import Message

logger = logging.getLogger(__name__)


class MessageHandlerResult(DynamicBaseModel):
    category: str
    persisted: bool
    streamed: bool
    message_id: str | None = None
    reason: str | None = None


class MessageHandler:
    """
    消息处理器
    
    职责：
    1. 接收原始消息数据
    2. 分类消息（MessageClassifier）
    3. 应用持久化策略（MessagePersistencePolicy）
    4. 应用流式推送策略（MessageStreamPolicy）
    5. 执行相应操作
    
    使用示例：
        handler = MessageHandler(thread_id="xxx", project_id=1)
        await handler.handle_ai_message(
            content="我来帮您处理",
            tool_calls=[{"name": "read_file", ...}],
            metadata={"node_source": "worker"}
        )
    """

    def __init__(self, thread_id: str, project_id: int | None = None, run_id: str | None = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        self._last_logged_hash = None
        self._last_logged_time = 0

    async def handle_ai_message(
        self,
        content: str,
        tool_calls: list | None = None,
        thinking: str | None = None,
        metadata: dict | None = None,
    ) -> MessageHandlerResult:
        """
        处理 AI 助手消息
        
        Args:
            content: 消息内容
            tool_calls: 工具调用列表
            thinking: 思考内容（从 <think> 标签提取）
            metadata: 元数据（可能包含 source 标记）
            
        Returns:
            dict: 处理结果
            {
                "category": str,
                "persisted": bool,
                "streamed": bool,
                "message_id": str | None,
            }
        """
        # 1. 分类
        category = MessageClassifier.classify_ai_message(
            content=content,
            tool_calls=tool_calls,
            metadata=metadata,
        )

        # 2. 应用策略
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category,
            content=content,
            tool_calls=tool_calls,
            thinking=thinking,
        )

        logger.info(f"[UnifiedHandler] AI message classified as: {category.value}, persist={persist_data.should_persist}")

        stream_data = MessageStreamPolicy.apply_policy(
            category=category,
            content=content,
            metadata=metadata,
        )

        # 3. 去重检查
        if self._is_duplicate(category, content, tool_calls):
            logger.debug("[UnifiedHandler] Duplicate message detected, skipping")
            return MessageHandlerResult(
                category=category.value,
                persisted=False,
                streamed=False,
                message_id=None,
                reason="duplicate",
            )

        # 4. 持久化 + 即时推送到 Mobile
        message_id = None
        if persist_data.should_persist:
            message_id, seq = await self._persist_to_db(
                role="ai",
                content=persist_data.content,
                thinking=persist_data.thinking,
                tool_calls=persist_data.tool_calls,
                category=category.value,
                is_visible=category.is_visible_to_user,
            )
            # 即时推送：AI 消息产生时直接发到 Mobile，不经过 SQLite 中转
            # 注意：思考过程（INTERNAL_REASONING）不推送到 Mobile，Mobile UI 暂不展示思考过程
            if message_id and category.is_visible_to_user and category != MessageCategory.INTERNAL_REASONING:
                await self._push_to_mobile(
                    role="ai",
                    content=persist_data.content,
                    thinking=persist_data.thinking,
                    tool_calls=persist_data.tool_calls,
                    category=category.value,
                    status="completed",
                    sequence_number=seq,
                )

        # 5. 流式推送到 Web UI (Redis SSE)
        if stream_data.should_stream:
            await self._stream_to_frontend(
                content=stream_data.content,
                frontend_type=stream_data.frontend_type,
                category=category.value,
                metadata=metadata,
                tool_calls=persist_data.tool_calls,
            )

        return MessageHandlerResult(
            category=category.value,
            persisted=persist_data.should_persist,
            streamed=stream_data.should_stream,
            message_id=message_id,
        )

    async def handle_tool_output(
        self,
        tool_name: str,
        output: Any,
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> MessageHandlerResult:
        """
        处理工具输出消息
        
        Args:
            tool_name: 工具名称
            output: 工具输出内容
            tool_call_id: 工具调用 ID
            run_id: 运行 ID
            
        Returns:
            dict: 处理结果
        """
        # 1. 分类
        category = MessageClassifier.classify_tool_output(tool_name, output)

        content = str(output) if output else ""

        # 2. 应用策略
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

        logger.info(f"[UnifiedHandler] Tool {tool_name} output classified as: {category.value}, persist={persist_data.should_persist}")

        stream_data = MessageStreamPolicy.apply_policy(
            category=category,
            content=content,
        )

        # 3. 持久化 + 即时推送到 Mobile
        message_id = None
        if persist_data.should_persist:
            message_id, seq = await self._persist_to_db(
                role="tool",
                content=persist_data.content,
                category=category.value,
                action_type="tool_output",
                is_visible=category.is_visible_to_user,
                tool_call_id=persist_data.tool_call_id,
                tool_name=persist_data.tool_name,
            )
            # 即时推送：工具输出对用户可见时直接发到 Mobile
            if message_id and category.is_visible_to_user:
                await self._push_to_mobile(
                    role="tool",
                    content=persist_data.content,
                    category=category.value,
                    action_type="tool_output",
                    status="completed",
                    sequence_number=seq,
                    tool_name=persist_data.tool_name,
                    tool_call_id=persist_data.tool_call_id,
                )

            # [Optimization] Also update the steps_snapshot of the parent AI message
            # This implements the "Cache-on-Save" pattern for fast historical loading
            try:
                from app.infrastructure.queue.factory import get_scheduler
                get_scheduler().send_task(
                    "engine_snapshot_steps",
                    kwargs={
                        "thread_id": self.thread_id,
                        "project_id": self.project_id,
                        "run_id": run_id,
                        "steps": [{
                            "tool": tool_name,
                            "input": {},  # Input was already recorded in AIMessage
                            "details": content,
                            "status": "success",
                            "tool_call_id": tool_call_id,
                        }]
                    }
                )
            except Exception as e:
                logger.warning(f"[UnifiedHandler] Failed to trigger incremental snapshot: {e}")

        # 4. 流式推送到 Web UI (Redis SSE)
        if stream_data.should_stream:
            await self._stream_to_frontend(
                content=content,
                frontend_type=stream_data.frontend_type,
                category=category.value,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )

        return MessageHandlerResult(
            category=category.value,
            persisted=persist_data.should_persist,
            streamed=stream_data.should_stream,
            message_id=message_id,
        )

    async def handle_user_message(self, content: str, metadata: dict | None = None) -> MessageHandlerResult:
        """
        处理用户消息
        
        Args:
            content: 消息内容
            metadata: 元数据
            
        Returns:
            dict: 处理结果
        """
        category = MessageCategory.USER

        # 用户消息只持久化，不推送到 Mobile（Mobile 已做乐观更新）
        message_id, _ = await self._persist_to_db(
            role="human",
            content=content,
            category=category.value,
            is_visible=True,
        )

        # 仍推送到 Web UI (Redis SSE) 以便桌面端看到
        await self._stream_to_frontend(
            content=content,
            frontend_type="human",
            category=category.value,
        )

        return MessageHandlerResult(
            category=category.value,
            persisted=True,
            streamed=True,
            message_id=message_id,
        )

    async def handle_hitl_request(
        self,
        request_type: str,
        prompt: str,
        request_id: str,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
    ) -> MessageHandlerResult:
        """
        处理人机交互请求（HITL）

        1. 持久化到本地 DB（status='waiting_human'）
        2. 即时推送到 Gateway（不等待批量同步）

        Args:
            request_type: 请求类型（text/choice/confirmation/approval）
            prompt: 提示内容
            request_id: HITL 请求 ID
            options: 选项列表
            context: 上下文
            default_value: 默认值

        Returns:
            MessageHandlerResult: 处理结果
        """
        content = json.dumps({
            "id": request_id,
            "type": request_type,
            "prompt": prompt,
            "options": options,
            "context": context,
            "default_value": default_value,
        }, ensure_ascii=False)

        # 1. 持久化到本地 DB
        message_id, seq = await self._persist_to_db(
            role="system",
            content=content,
            category="hitl_request",
            action_type="human_request",
            status="waiting_human",
            is_visible=True,
        )

        # 2. 即时推送到 Mobile（通过统一入口 _push_to_mobile，替代 _notify_gateway_urgent）
        await self._push_to_mobile(
            role="system",
            content=content,
            category="hitl_request",
            action_type="human_request",
            status="waiting_human",
            sequence_number=seq,
        )

        return MessageHandlerResult(
            category="hitl_request",
            persisted=True,
            streamed=True,
            message_id=message_id,
        )

    async def handle_error(self, error: Exception) -> MessageHandlerResult:
        """
        处理异常上报
        
        集中解析错误类型，决定是否入库，并立即推送到前端。
        """
        from app.core.engine.error_handler import LLMErrorHandler
        from app.models.schemas.events import QuotaExhaustedEvent
        from app.core.monitoring.activity import activity_monitor

        # 1. 自动解析分类
        classification = LLMErrorHandler.classify_exception(error)
        
        # 默认作为系统错误
        category = MessageCategory.ERROR_SYSTEM
        
        # 特殊情况映射为业务错误（需要入库）
        if classification.error_type in ["business_logic", "workflow_error"]:
            category = MessageCategory.ERROR_BUSINESS

        logger.warning(f"[UnifiedHandler] Handling error: {classification.error_type} (cat={category.value})")

        # 2. 持久化（仅对 ERROR_BUSINESS）+ 推送到 Mobile + Web UI
        message_id = None
        if category == MessageCategory.ERROR_BUSINESS:
            # 持久化使用 Markdown 格式（Web UI 支持）
            error_markdown = f"**{classification.title}**\n\n{classification.message}\n\n*Hint: {classification.hint}*"
            message_id, _ = await self._persist_to_db(
                role="ai",
                content=error_markdown,
                category=category.value,
                is_visible=True
            )

        # 推送到 Mobile（统一走 MobileErrorNotifier）
        from app.core.engine.message.mobile_notifier import MobileErrorNotifier
        await MobileErrorNotifier(self).push(classification)

        # 3. 流式推送到 Web UI (Redis SSE)
        # 3.1 推送特定弹窗事件 (429 Quota)
        if classification.error_type == "quota_exhausted":
            try:
                if activity_monitor and hasattr(activity_monitor, "client"):
                    await activity_monitor.client.publish(
                        f"chat:{self.thread_id}:events",
                        QuotaExhaustedEvent(
                            title=classification.title,
                            message=classification.message,
                            hint=classification.hint
                        ).model_dump_json()
                    )
            except Exception as e:
                logger.error(f"[UnifiedHandler] Failed to publish QuotaExhaustedEvent: {e}")

        # 3.2 始终推送通用错误卡片 (SSE frontend_type="error")
        await self._stream_to_frontend(
            content=f"**{classification.title}**\n{classification.message}",
            frontend_type="error",
            category=category.value,
            metadata={
                "error_type": classification.error_type,
                "hint": classification.hint,
                "is_terminal": classification.is_terminal
            }
        )

        return MessageHandlerResult(
            category=category.value,
            persisted=category == MessageCategory.ERROR_BUSINESS,
            streamed=True,
            message_id=message_id,
        )

    def _is_duplicate(
        self,
        category: MessageCategory,
        content: str,
        tool_calls: list | None,
    ) -> bool:
        """
        检查是否是重复消息（简单去重）
        
        基于内容的哈希和时间窗口判断
        """
        import hashlib

        content_hash = hashlib.md5(
            f"{category.value}:{content}:{str(tool_calls)}".encode()
        ).hexdigest()[:16]

        current_time = time.time()

        # 2 秒内的相同内容视为重复
        if (
            content_hash == self._last_logged_hash
            and (current_time - self._last_logged_time) < 2.0
        ):
            return True

        self._last_logged_hash = content_hash
        self._last_logged_time = current_time
        return False

    async def _persist_to_db(
        self,
        role: str,
        content: str | None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        action_type: str = "text",
        status: str = "completed",
        is_visible: bool = True,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> tuple[str | None, int]:
        """
        持久化消息到数据库。

        只做 INSERT，不触发任何推送。推送由调用方根据消息类型决定。
        返回 (message_id, sequence_number)。

        注意：使用数据库查询获取下一个序列号，避免并发 Agent run 导致 sequence_number 冲突。
        """
        if not content and not thinking and not tool_calls:
            logger.warning(f"[UnifiedHandler] Skipping persist for {role}: no content, thinking, or tool_calls")
            return None, 0

        try:
            # 使用数据库查询获取下一个序列号，确保并发安全
            from app.infrastructure.database.sql.database import session_scope

            async with session_scope() as session:
                stmt = select(func.max(Message.sequence_number)).where(Message.thread_id == self.thread_id)
                max_seq = (await session.execute(stmt)).scalar() or 0
                seq = max_seq + 1

            logger.info(f"[UnifiedHandler] Persisting {role} message (seq={seq}, cat={category})")

            # 直接同步调用持久化核心函数（不再走 Huey 队列）
            from app.core.engine.tasks import _persist_message_impl
            await _persist_message_impl(
                thread_id=self.thread_id,
                project_id=self.project_id,
                role=role,
                content=content or "",
                thinking=thinking,
                tool_calls=tool_calls,
                category=category,
                action_type=action_type,
                status=status,
                sequence_number=seq,
                run_id=self.run_id,
                is_visible=is_visible,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )

            msg_id = f"msg-{self.thread_id}-{seq}"
            return msg_id, seq

        except Exception as e:
            logger.error(f"[UnifiedHandler] Failed to persist message: {e}")
            return None, 0

    async def _push_to_mobile(
        self,
        role: str,
        content: str | None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        action_type: str = "text",
        status: str = "completed",
        sequence_number: int = 0,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """
        即时推送单条消息到 Mobile（通过 Gateway WebSocket）。

        在消息产生时立即调用，不经过 SQLite 中转。
        只有 AI 产生的消息（role != human）且对用户可见的消息才需要推送。
        """
        if role == "human":
            return

        try:
            from app.core.evocloud import evocloud_manager
            from app.core.engine.message.mobile_schema import MobileSyncMessage

            if not evocloud_manager.link or not evocloud_manager.link.is_connected():
                logger.debug("[UnifiedHandler] WebSocket not connected, skipping mobile push")
                return

            msg = MobileSyncMessage(
                id=f"msg-{self.thread_id}-{sequence_number}",
                thread_id=self.thread_id,
                project_id=self.project_id or 0,
                role=role,  # type: ignore[arg-type]
                content=content or "",
                thinking=thinking,
                created_at=int(time.time()),
                sequence_number=sequence_number,
                action_type=action_type,
                status=status,  # type: ignore[arg-type]
                category=category,
                tool_calls=tool_calls,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )

            await evocloud_manager.link.send_message({
                "type": "message_sync",
                "data": msg.model_dump(exclude_none=True),
            })

            logger.info(f"[UnifiedHandler] Pushed to mobile: seq={sequence_number}, role={role}, action={action_type}")

        except Exception as e:
            logger.warning(f"[UnifiedHandler] Failed to push to mobile: {e}")

    async def _stream_to_frontend(
        self,
        content: str,
        frontend_type: str,
        category: str,
        metadata: dict | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list | None = None,
    ):
        """
        推送消息到前端（SSE/WebSocket）
        """
        try:

            from app.core.monitoring.activity import activity_monitor
            from app.core.tools.registry import get_tool_friendly_name
            from app.models.schemas.events import MessageEvent

            if not activity_monitor or not hasattr(activity_monitor, "client"):
                return

            msg_data = {
                "id": f"temp-{time.time()}",
                "role": frontend_type,
                "content": content,
                "type": frontend_type,
                "category": category,
                "timestamp": int(time.time() * 1000),
                "tool_calls": tool_calls,
            }

            if metadata:
                msg_data["metadata"] = metadata

            if tool_name:
                # 传递原始工具名
                msg_data["tool_name"] = tool_name
                # 传递工具调用 ID 以实现实时折叠一致性
                msg_data["tool_call_id"] = tool_call_id
                # 同时传递友好显示名称（如果可用）
                friendly_name = get_tool_friendly_name(tool_name, lang="zh")
                if friendly_name:
                    msg_data["tool_name_display"] = friendly_name

            channel = f"chat:{self.thread_id}:events"
            message = MessageEvent(data=msg_data).model_dump_json()

            await activity_monitor.client.publish(channel, message)

        except Exception as e:
            logger.warning(f"[UnifiedHandler] Failed to stream message: {e}")
