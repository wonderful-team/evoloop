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
from app.core.tools.registry import get_tool_metadata
from app.i18n.service import i18n

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
        parent_id: str | None = None,
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
                parent_id=parent_id,
            )
            
            # 只有用户可见且不是纯内部思考的消息才推送到 Mobile
            if message_id and category.is_visible_to_user and category != MessageCategory.INTERNAL_REASONING:
                await self._dispatch_block(
                    role="ai", content=persist_data.content, thinking=persist_data.thinking,
                    tool_calls=persist_data.tool_calls, category=category.value,
                    status="completed", sequence_number=seq, channels={"mobile"},
                    parent_id=parent_id or await self._repository.get_last_message_id(), # Fallback for stream
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role="ai", content=stream_data.content,
                category=category.value, metadata=metadata,
                tool_calls=persist_data.tool_calls, 
                thinking=thinking,
                sequence_number=seq if persist_data.should_persist else 0,
                status="streaming" if persist_data.should_persist else "completed",
                channels={"sse"},
                parent_id=parent_id or await self._repository.get_last_message_id(),
            )

        return MessageHandlerResult(
            category=category.value, persisted=persist_data.should_persist,
            streamed=stream_data.should_stream, message_id=message_id,
            sequence_number=seq,
        )

    async def handle_tool_start(
        self,
        tool_name: str,
        tool_call_id: str | None = None,
        input_data: dict | None = None,
        parent_id: str | None = None,
    ) -> MessageHandlerResult:
        """处理工具开始执行 — 预插入 running 状态记录"""
        # Build tool_meta for frontend rendering (canonical source)
        metadata = get_tool_metadata(tool_name)
        is_hidden = metadata.is_hidden
        
        # Categorize based on tool visibility
        category = MessageCategory.INTERNAL_TOOL_CALL if is_hidden else MessageCategory.TOOL_OUTPUT

        summary_template = metadata.summary_template
        display_name = None
        if summary_template and input_data:
            try:
                display_name = i18n.get(summary_template, **input_data)
            except (KeyError, TypeError):
                pass
        tool_meta = {
            "display_name": display_name,
            "affected_path_keys": metadata.affected_path_keys,
        }

        message_id = None
        seq = 0
        
        # Apply persistence policy
        if category.should_persist_to_db:
            message_id, seq = await self._repository.persist(
                role="tool",
                content="",
                category=category.value,
                action_type="tool_output",
                status="running",
                is_visible=True,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content_type="text",
                metadata={"tool_name": tool_name, "tool_call_id": tool_call_id, "input": input_data, "tool_meta": tool_meta},
                parent_id=parent_id,
            )

        # Push real-time "running" event if visible
        if category.is_visible_to_user:
            await self._dispatch_block(
                role="tool", content="", category=category.value,
                status="running", sequence_number=seq,
                tool_name=tool_name, tool_call_id=tool_call_id,
                metadata={"tool_meta": tool_meta, "input": input_data},
                channels={"sse", "mobile"}
            )

        logger.info(f"[MessageHandler] Tool start tracked: {tool_name} (seq={seq}, hidden={is_hidden})")
        return MessageHandlerResult(
            category=category.value, persisted=category.should_persist_to_db, 
            streamed=category.is_visible_to_user,
            message_id=message_id, sequence_number=seq,
        )

    async def handle_tool_output(
        self,
        tool_name: str,
        output: Any,
        tool_call_id: str | None = None,
        run_id: str | None = None,
        sequence_number: int | None = None,
    ) -> MessageHandlerResult:
        """处理工具输出消息 — 支持 UPDATE 已有 running 记录"""
        # Check tool visibility from registry
        tool_meta_registry = get_tool_metadata(tool_name)
        is_hidden = tool_meta_registry.is_hidden
        
        if is_hidden:
            category = MessageCategory.INTERNAL_TOOL_CALL
        else:
            category = MessageClassifier.classify_tool_output(tool_name, output)
            
        content = str(output) if output else ""
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category, content=content, tool_call_id=tool_call_id, tool_name=tool_name,
        )
        stream_data = MessageStreamPolicy.apply_policy(category=category, content=content)

        logger.info(f"[MessageHandler] Tool {tool_name} output classified as: {category.value}, persist={persist_data.should_persist}")

        message_id = None
        seq = sequence_number or 0

        if seq and persist_data.should_persist:
            # UPDATE existing running record
            updated = await self._repository.update(
                sequence_number=sequence_number,
                status="completed",
                content=persist_data.content,
                meta_data={"tool_name": tool_name, "tool_call_id": tool_call_id, "output": output},
            )
            if updated:
                message_id = f"msg-{self.thread_id}-{sequence_number}"
                if category.is_visible_to_user:
                    await self._dispatch_block(
                        role="tool", content=persist_data.content, category=category.value,
                        status="completed", sequence_number=sequence_number,
                        tool_name=persist_data.tool_name, tool_call_id=persist_data.tool_call_id,
                        channels={"mobile"}
                    )
        elif persist_data.should_persist:
            # Fallback: INSERT new record (backward compatibility)
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
            sequence_number=seq,
        )

    async def handle_tool_error(
        self,
        tool_name: str,
        error: Exception,
        tool_call_id: str | None = None,
        sequence_number: int | None = None,
    ) -> MessageHandlerResult:
        """处理工具执行错误 — 将 running 记录标记为 failed"""
        content = str(error) if error else "Tool execution failed"
        seq = sequence_number or 0

        if sequence_number:
            await self._repository.update(
                sequence_number=sequence_number,
                status="failed",
                content=content,
                meta_data={"tool_name": tool_name, "tool_call_id": tool_call_id, "error": content},
            )

        return MessageHandlerResult(
            category="tool_error", persisted=bool(sequence_number),
            streamed=False, message_id=None, sequence_number=seq,
        )

    async def handle_user_message(self, content: str, metadata: dict | None = None) -> MessageHandlerResult:
        """处理用户消息"""
        category = MessageCategory.USER
        message_id, seq = await self._repository.persist(
            role="human", content=content, category=category.value,
            is_visible=True, content_type="text",
            metadata=metadata,
            parent_id=None, # User message parent is resolved in repository if None
        )
        await self._dispatch_block(
            role="human", content=content, category=category.value,
            sequence_number=seq, channels={"sse"}
        )
        return MessageHandlerResult(
            category=category.value, persisted=True, streamed=True, 
            message_id=message_id, sequence_number=seq
        )

    async def handle_hitl_request(
        self,
        request_type: str,
        prompt: str,
        request_id: str,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        parent_id: str | None = None,
    ) -> MessageHandlerResult:
        """处理人机交互请求（HITL）"""
        logger.info(f"[MessageHandler] Handling HITL request: {request_id} (tool={tool_name})")
        content = json.dumps({
            "id": request_id, "type": request_type, "prompt": prompt,
            "options": options, "context": context, "default_value": default_value,
        }, ensure_ascii=False)

        # Generate tool_meta if tool information is provided
        metadata = {}
        if tool_name:
            from app.core.tools.registry import get_tool_metadata
            from app.i18n.service import i18n
            tool_meta = get_tool_metadata(tool_name)
            if tool_meta and tool_meta.summary_template:
                metadata["tool_meta"] = {
                    "name": tool_name,
                    "display_name": i18n.get(tool_meta.summary_template, request_type=request_type, prompt=prompt),
                }

        message_id, seq = await self._repository.persist(
            role="system", content=content, category=MessageCategory.HITL_REQUEST.value,
            action_type="human_request", status="waiting_human",
            is_visible=True, content_type="json",
            tool_call_id=tool_call_id or request_id, # Fallback to request_id
            tool_name=tool_name,
            metadata=metadata if metadata else None,
            parent_id=parent_id,
        )
        await self._dispatch_block(
            role="system", content=content, category=MessageCategory.HITL_REQUEST.value,
            status="waiting_human", sequence_number=seq,
            tool_name=tool_name, tool_call_id=tool_call_id or request_id,
            metadata=metadata if metadata else None,
            channels={"sse", "mobile"},
            parent_id=parent_id,
        )
        return MessageHandlerResult(category=MessageCategory.HITL_REQUEST.value, persisted=True, streamed=True, message_id=message_id)

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
            if not self._publisher:
                self._publisher = MessagePublisher(thread_id=self.thread_id, project_id=self.project_id)
            await self._publisher.publish(QuotaExhaustedEvent(
                thread_id=self.thread_id,
                title=classification.title,
                message=classification.message,
                hint=classification.hint
            ))
        
        elif classification.error_type == "llm_auth":
            from app.models.schemas.events import LLMAuthErrorEvent
            if not self._publisher:
                self._publisher = MessagePublisher(thread_id=self.thread_id, project_id=self.project_id)
            await self._publisher.publish(LLMAuthErrorEvent(
                thread_id=self.thread_id,
                title=classification.title,
                message=classification.message
            ))

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

        # [STATUS FIX] Ensure frontend transitions to error state
        from app.models.schemas.events import StatusEvent
        if not self._publisher:
            self._publisher = MessagePublisher(thread_id=self.thread_id, project_id=self.project_id)
        await self._publisher.publish(StatusEvent(thread_id=self.thread_id, status="error"))

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
        parent_id: str | None = None,
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
            thinking=thinking,
            tool_calls=tool_calls,
            status=status,  # type: ignore[arg-type]
            is_visible=True,
            sequence_number=sequence_number,
            created_at=datetime.now().isoformat(),
            parent_id=parent_id,
            meta_data={
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
        """分发 LLM Token 片段"""
        if not token_buffer: return
        from app.models.schemas.events import TokenEvent
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(TokenEvent(thread_id=thread_id, content=token_buffer))

    @staticmethod
    async def stream_thinking(thread_id: str, thinking_delta: str) -> None:
        """分发 AI 思考过程片段"""
        if not thinking_delta: return
        from app.models.schemas.events import ThinkingEvent
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(ThinkingEvent(thread_id=thread_id, content=thinking_delta))

    @staticmethod
    async def stream_progress(
        thread_id: str, 
        message: str, 
        progress: int | None = None, 
        status: str = "running",
        metadata: dict | None = None
    ) -> None:
        """分发任务/工具执行进度"""
        from app.models.schemas.events import ProgressEvent
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(ProgressEvent(
            thread_id=thread_id,
            status=status, # type: ignore
            message=message,
            progress=progress,
            metadata=metadata or {}
        ))
