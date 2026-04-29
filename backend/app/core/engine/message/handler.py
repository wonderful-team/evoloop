"""
MessageHandler - 消息处理器（Orchestrator）

整合分类、持久化、推送策略的统一入口。
替代原来分散在各 callback 中的处理逻辑。

职责拆分：
- MessageClassifier: 分类（纯函数，已存在）
- MessageRepository: 数据库操作（repository.py）
- MessageDeduplicator: 去重（deduplicator.py）
- MessagePublisher: 推送（publisher.py）
- MessageHandler: 编排器（此文件）
"""
import json
import logging
import time
from datetime import datetime
from typing import Any

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.deduplicator import MessageDeduplicator
from app.core.engine.message.persistence import MessagePersistencePolicy
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.repository import MessageRepository
from app.core.engine.message.schemas import MessageBlock
from app.core.engine.message.schemas import MessageHandlerResult
from app.core.engine.message.stream import MessageStreamPolicy
from app.core.engine.message.reasoning import build_thinking_blocks, infer_thinking_type

logger = logging.getLogger(__name__)


class MessageHandler:
    """
    消息处理器 — 编排器

    职责：
    1. 接收原始消息数据
    2. 分类消息（MessageClassifier）
    3. 应用持久化策略（MessagePersistencePolicy）
    4. 应用流式推送策略（MessageStreamPolicy）
    5. 调用 Repository / Deduplicator / Publisher 执行操作
    """

    def __init__(self, thread_id: str, project_id: int | None = None, run_id: str | None = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        self._publisher: MessagePublisher | None = None
        self._stream_seq = int(time.time() * 1000)

        # Delegated components
        self._repository = MessageRepository(thread_id, project_id, run_id)
        self._deduplicator = MessageDeduplicator()

    async def handle_ai_message(
        self,
        content: str,
        tool_calls: list | None = None,
        thinking: str | None = None,
        metadata: dict | None = None,
    ) -> MessageHandlerResult:
        """处理 AI 助手消息"""
        category = MessageClassifier.classify_ai_message(
            content=content, tool_calls=tool_calls, metadata=metadata,
        )
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category, content=content, tool_calls=tool_calls, thinking=thinking,
        )
        stream_data = MessageStreamPolicy.apply_policy(
            category=category, content=content, metadata=metadata,
        )

        logger.info(f"[MessageHandler] AI message classified as: {category.value}, persist={persist_data.should_persist}")

        if self._deduplicator.is_duplicate(category, content, tool_calls):
            logger.debug("[MessageHandler] Duplicate message detected, skipping")
            return MessageHandlerResult(category=category.value, persisted=False, streamed=False, reason="duplicate")

        message_id = None
        seq = 0

        # Determine thinking type from metadata
        thinking_type = infer_thinking_type(metadata)

        if persist_data.should_persist:
            message_id, seq = await self._repository.persist(
                role="ai",
                content=persist_data.content,
                thinking=persist_data.thinking,
                tool_calls=persist_data.tool_calls,
                category=category.value,
                is_visible=category.is_visible_to_user,
                content_type="text",
                metadata=metadata,
            )
            
            # 只有用户可见且不是纯内部思考的消息才推送到 Mobile
            if message_id and category.is_visible_to_user and category != MessageCategory.INTERNAL_REASONING:
                await self._dispatch_block(
                    role="ai", content=persist_data.content, thinking=persist_data.thinking,
                    tool_calls=persist_data.tool_calls, category=category.value,
                    status="completed", sequence_number=seq, channels={"mobile"}
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role="ai", content=stream_data.content,
                category=category.value, metadata=metadata,
                tool_calls=persist_data.tool_calls, thinking=thinking,
                sequence_number=seq if persist_data.should_persist else 0,
                status="streaming" if persist_data.should_persist else "completed",
                channels={"sse"}
            )

        return MessageHandlerResult(
            category=category.value, persisted=persist_data.should_persist,
            streamed=stream_data.should_stream, message_id=message_id,
        )

    async def handle_tool_output(
        self,
        tool_name: str,
        output: Any,
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> MessageHandlerResult:
        """处理工具输出消息"""
        category = MessageClassifier.classify_tool_output(tool_name, output)
        content = str(output) if output else ""
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category, content=content, tool_call_id=tool_call_id, tool_name=tool_name,
        )
        stream_data = MessageStreamPolicy.apply_policy(category=category, content=content)

        logger.info(f"[MessageHandler] Tool {tool_name} output classified as: {category.value}, persist={persist_data.should_persist}")

        message_id = None
        seq = 0
        if persist_data.should_persist:
            message_id, seq = await self._repository.persist(
                role="tool", content=persist_data.content, category=category.value,
                action_type="tool_output", is_visible=category.is_visible_to_user,
                tool_call_id=persist_data.tool_call_id, tool_name=persist_data.tool_name,
                content_type="text",
                metadata={"tool_name": tool_name, "tool_call_id": tool_call_id},
            )
            if message_id and category.is_visible_to_user:
                await self._dispatch_block(
                    role="tool", content=persist_data.content, category=category.value,
                    status="completed", sequence_number=seq,
                    tool_name=persist_data.tool_name, tool_call_id=persist_data.tool_call_id,
                    channels={"mobile"}
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role="tool", content=content, category=category.value,
                tool_name=tool_name, tool_call_id=tool_call_id,
                sequence_number=seq if persist_data.should_persist else 0,
                channels={"sse"}
            )

        return MessageHandlerResult(
            category=category.value, persisted=persist_data.should_persist,
            streamed=stream_data.should_stream, message_id=message_id,
        )

    async def handle_user_message(self, content: str, metadata: dict | None = None) -> MessageHandlerResult:
        """处理用户消息"""
        category = MessageCategory.USER
        message_id, seq = await self._repository.persist(
            role="human", content=content, category=category.value,
            is_visible=True, content_type="text",
            metadata=metadata,
        )
        await self._dispatch_block(
            role="human", content=content, category=category.value,
            sequence_number=seq, channels={"sse"}
        )
        return MessageHandlerResult(category=category.value, persisted=True, streamed=True, message_id=message_id)

    async def handle_hitl_request(
        self,
        request_type: str,
        prompt: str,
        request_id: str,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
    ) -> MessageHandlerResult:
        """处理人机交互请求（HITL）"""
        content = json.dumps({
            "id": request_id, "type": request_type, "prompt": prompt,
            "options": options, "context": context, "default_value": default_value,
        }, ensure_ascii=False)

        message_id, seq = await self._repository.persist(
            role="system", content=content, category="hitl_request",
            action_type="human_request", status="waiting_human",
            is_visible=True, content_type="json",
        )
        await self._dispatch_block(
            role="system", content=content, category="hitl_request",
            status="waiting_human", sequence_number=seq,
            channels={"sse", "mobile"}
        )
        return MessageHandlerResult(category="hitl_request", persisted=True, streamed=True, message_id=message_id)

    async def handle_error(self, error: Exception) -> MessageHandlerResult:
        """处理异常上报"""
        from app.core.engine.error_handler import LLMErrorHandler

        classification = LLMErrorHandler.classify_exception(error)
        category = MessageCategory.ERROR_BUSINESS if classification.error_type in ["business_logic", "workflow_error"] else MessageCategory.ERROR_SYSTEM

        logger.warning(f"[MessageHandler] Handling error: {classification.error_type} (cat={category.value})")

        message_id = None
        if category == MessageCategory.ERROR_BUSINESS:
            error_markdown = f"**{classification.title}**\n\n{classification.message}\n\n*Hint: {classification.hint}*"
            message_id, _ = await self._repository.persist(
                role="ai", content=error_markdown, category=category.value,
                is_visible=True, content_type="markdown",
            )

        from app.core.engine.message.mobile_notifier import MobileErrorNotifier
        await MobileErrorNotifier(self).push(classification)

        if classification.error_type == "quota_exhausted":
            from app.models.schemas.events import QuotaExhaustedEvent
            from app.core.engine.message.event_bus import get_event_bus
            await get_event_bus().publish(
                f"chat:{self.thread_id}:events",
                QuotaExhaustedEvent(
                    title=classification.title, message=classification.message, hint=classification.hint
                ).model_dump_json()
            )

        await self._dispatch_block(
            role="system", content=f"**{classification.title}**\n{classification.message}",
            category=category.value,
            metadata={
                "error_type": classification.error_type,
                "hint": classification.hint,
                "is_terminal": classification.is_terminal
            },
            channels={"sse"}
        )
        return MessageHandlerResult(
            category=category.value, persisted=category == MessageCategory.ERROR_BUSINESS,
            streamed=True, message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _dispatch_block(
        self,
        role: str,
        content: str | None,
        thinking: str | None = None,
        tool_calls: list | None = None,
        category: str = "",
        status: str = "completed",
        sequence_number: int = 0,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict | None = None,
        channels: set[str] | None = None,
    ) -> None:
        """统一构造 MessageBlock 并分发"""
        if sequence_number == 0:
            self._stream_seq += 1
            sequence_number = self._stream_seq

        block = MessageBlock(
            id=f"msg-{self.thread_id}-{sequence_number}",
            thread_id=self.thread_id,
            run_id=self.run_id,
            role=role,  # type: ignore[arg-type]
            category=category,
            content=content or "",
            thinking=build_thinking_blocks(thinking),
            tool_calls=tool_calls,
            status=status,  # type: ignore[arg-type]
            is_visible=True,
            sequence_number=sequence_number,
            created_at=datetime.now().isoformat(),
            metadata={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                **(metadata or {}),
            },
        )
        
        if not self._publisher:
            self._publisher = MessagePublisher(thread_id=self.thread_id, project_id=self.project_id)
        
        await self._publisher.publish(block, channels=channels)

    @staticmethod
    async def stream_token(thread_id: str, token_buffer: str) -> None:
        """
        Stream a token buffer via unified MessagePublisher.
        """
        if not token_buffer or not thread_id:
            return

        from app.core.engine.message.schemas import StreamEvent, StreamEventType
        publisher = MessagePublisher(thread_id=thread_id)
        
        # 使用统一的 StreamEvent 协议，不再直接操作 Redis 通道
        await publisher.publish(StreamEvent(
            type=StreamEventType.TOKEN,
            data={"content": token_buffer}
        ))
