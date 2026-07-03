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
from typing import Any

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.deduplicator import MessageDeduplicator
from app.core.engine.message.persistence import MessagePersistencePolicy
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.repository import MessageRepository
from app.core.engine.message.schemas import MessageHandlerResult
from app.core.engine.message.stream import MessageStreamPolicy
from app.core.tools.registry import get_tool_metadata
from app.models.schemas.events import (
    LLMAuthErrorEvent,
    ProgressEvent,
    QuotaExhaustedEvent,
    StatusEvent,
    ThinkingEvent,
    TokenEvent,
)

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

    def __init__(
        self, thread_id: str, project_id: int | None = None, run_id: str | None = None
    ):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        self._publisher: MessagePublisher | None = None
        self._stream_seq = int(time.time() * 1000)

        # Exposed for downstream consumers (e.g. FinishNode) that need the
        # DB-assigned message_id and sequence_number from the last persist.
        self.last_persisted_message_id: str | None = None
        self.last_persisted_sequence: int = 0

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
        message_id: str | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        """处理 AI 助手消息"""
        category = MessageClassifier.classify_ai_message(
            content=content,
            tool_calls=tool_calls,
            metadata=metadata,
        )
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category,
            content=content,
            tool_calls=tool_calls,
            thinking=thinking,
        )
        stream_data = MessageStreamPolicy.apply_policy(
            category=category,
            content=content,
            metadata=metadata,
        )

        logger.info(
            f"[MessageHandler] AI message classified as: {category.value}, persist={persist_data.should_persist}"
        )

        # Finish 节点的审计 LLM 输出不应在消息列表中展示，也不应推送到前端
        _is_finish_message = node_source == "finish"

        if self._deduplicator.is_duplicate(category, content, tool_calls):
            logger.debug("[MessageHandler] Duplicate message detected, skipping")
            return MessageHandlerResult(
                category=category.value,
                persisted=False,
                streamed=False,
                reason="duplicate",
            )

        msg_id = message_id
        seq = 0

        effective_parent_id = parent_id or await self._repository.get_last_message_id()

        if persist_data.should_persist:
            # --- [Phase 2] 自动提取 AI 产出物引用 ---
            from app.core.engine.message.extractor import attachment_extractor

            extracted_refs = attachment_extractor.extract_from_ai_response(
                content=persist_data.content
            )

            dev_key, dev_name = self._get_device_attribution()
            msg_id, seq = await self._repository.persist(
                role="ai",
                content=persist_data.content,
                thinking=persist_data.thinking,
                tool_calls=persist_data.tool_calls,
                category=category.value,
                is_visible=category.is_visible_to_user and not _is_finish_message,
                content_type="text",
                metadata=metadata,
                node_source=node_source,
                parent_id=effective_parent_id,
                references=extracted_refs,  # 挂载提取到的引用
                message_id=msg_id,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )

            # 只有用户可见且不是纯内部思考的消息才推送到 Mobile
            if (
                msg_id
                and category.is_visible_to_user
                and not _is_finish_message
                and category != MessageCategory.INTERNAL_REASONING
            ):
                await self._dispatch_block(
                    role="ai",
                    content=persist_data.content,
                    thinking=persist_data.thinking,
                    tool_calls=persist_data.tool_calls,
                    category=category.value,
                    status="completed",
                    sequence_number=seq,
                    channels={"mobile"},
                    parent_id=effective_parent_id,
                    message_id=msg_id,
                )

        if stream_data.should_stream and not _is_finish_message:
            await self._dispatch_block(
                role="ai",
                content=stream_data.content,
                category=category.value,
                metadata=metadata,
                tool_calls=persist_data.tool_calls,
                thinking=thinking,
                sequence_number=seq if persist_data.should_persist else 0,
                status="streaming" if persist_data.should_persist else "completed",
                references=extracted_refs if persist_data.should_persist else None,
                channels={"sse"},
                parent_id=effective_parent_id,
                message_id=msg_id,
            )

        self.last_persisted_message_id = msg_id
        self.last_persisted_sequence = seq
        return MessageHandlerResult(
            category=category.value,
            persisted=persist_data.should_persist,
            streamed=stream_data.should_stream,
            message_id=msg_id,
            sequence_number=seq,
        )

    async def handle_tool_start(
        self,
        tool_name: str,
        tool_call_id: str | None = None,
        input_data: dict | None = None,
        parent_id: str | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        """处理工具开始执行 — 预插入 running 状态记录"""
        # Build tool_meta for frontend rendering (canonical source)
        metadata = get_tool_metadata(tool_name)
        is_hidden = metadata.is_hidden

        # Categorize based on tool visibility
        category = (
            MessageCategory.INTERNAL_TOOL_CALL
            if is_hidden
            else MessageCategory.TOOL_OUTPUT
        )

        display_name = metadata.get_display_name(tool_name, input_data)
        tool_meta = {
            "display_name": display_name,
            "affected_path_keys": metadata.affected_path_keys,
        }

        message_id = None
        seq = 0

        effective_parent_id = parent_id or await self._repository.get_last_message_id()

        # Apply persistence policy
        if category.should_persist_to_db:
            dev_key, dev_name = self._get_device_attribution()
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
                metadata={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "input": input_data,
                    "tool_meta": tool_meta,
                },
                node_source=node_source,
                parent_id=effective_parent_id,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )

        # Push real-time "running" event to SSE only; Mobile gets only the terminal state
        if category.is_visible_to_user:
            await self._dispatch_block(
                role="tool",
                content="",
                category=category.value,
                status="running",
                sequence_number=seq,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"tool_meta": tool_meta, "input": input_data},
                channels={"sse"},
                parent_id=effective_parent_id,
                message_id=message_id,
            )

        logger.info(
            f"[MessageHandler] Tool start tracked: {tool_name} (seq={seq}, hidden={is_hidden})"
        )
        return MessageHandlerResult(
            category=category.value,
            persisted=category.should_persist_to_db,
            streamed=category.is_visible_to_user,
            message_id=message_id,
            sequence_number=seq,
        )

    async def handle_tool_output(
        self,
        tool_name: str,
        output: Any,
        tool_call_id: str | None = None,
        run_id: str | None = None,
        sequence_number: int | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        """处理工具输出消息 — 支持 UPDATE 已有 running 记录"""
        # Fetch tool metadata and input to rebuild tool_meta
        metadata_registry = get_tool_metadata(tool_name)
        input_data = await self._repository.resolve_tool_input(
            tool_call_id, tool_name=tool_name
        )

        # 从 ToolResult 中读取 result_meta（evoloop_tool 装饰器已渲染）
        result_meta = {}
        display_name = ""
        if hasattr(output, "meta") and isinstance(output.meta, dict):
            result_meta = output.meta
        if hasattr(output, "display_name"):
            display_name = output.display_name

        # 兜底与归一化渲染：如果装饰器没有渲染，或我们需要最新的摘要
        if not display_name or result_meta:
            summary_args = {**input_data, **result_meta}
            display_name = metadata_registry.get_display_name(tool_name, summary_args)

        tool_meta = {
            "display_name": display_name,
            "affected_path_keys": metadata_registry.affected_path_keys,
        }

        if metadata_registry.is_hidden:
            category = MessageCategory.INTERNAL_TOOL_CALL
        else:
            category = MessageClassifier.classify_tool_output(
                tool_name, output, metadata=result_meta
            )

        content = str(output) if output else ""
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        stream_data = MessageStreamPolicy.apply_policy(
            category=category, content=content
        )

        logger.info(
            f"[MessageHandler] Tool {tool_name} output classified as: {category.value}, persist={persist_data.should_persist}"
        )

        message_id = None
        seq = sequence_number or 0

        metadata = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": input_data,
            "output": output,
            "tool_meta": tool_meta,
        }

        if seq and persist_data.should_persist:
            # UPDATE existing running record
            update_result = await self._repository.update(
                sequence_number=seq,
                status="completed",
                content=persist_data.content,
                node_source=node_source,
                # We overwrite meta_data with the full set to ensure it's complete
                meta_data=metadata,
            )
            if update_result:
                message_id = update_result  # UUID string from repository.update()
                if category.is_visible_to_user:
                    await self._dispatch_block(
                        role="tool",
                        content=persist_data.content,
                        category=category.value,
                        status="completed",
                        sequence_number=seq,
                        tool_name=persist_data.tool_name,
                        tool_call_id=persist_data.tool_call_id,
                        metadata=metadata,
                        channels={"mobile"},
                        message_id=message_id,
                    )
        elif persist_data.should_persist:
            # Fallback: INSERT new record (backward compatibility)
            dev_key, dev_name = self._get_device_attribution()
            message_id, seq = await self._repository.persist(
                role="tool",
                content=persist_data.content,
                category=category.value,
                action_type="tool_output",
                is_visible=category.is_visible_to_user,
                tool_call_id=persist_data.tool_call_id,
                tool_name=persist_data.tool_name,
                content_type="text",
                metadata=metadata,
                node_source=node_source,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )
            if message_id and category.is_visible_to_user:
                await self._dispatch_block(
                    role="tool",
                    content=persist_data.content,
                    category=category.value,
                    status="completed",
                    sequence_number=seq,
                    tool_name=persist_data.tool_name,
                    tool_call_id=persist_data.tool_call_id,
                    metadata=metadata,
                    channels={"mobile"},
                    message_id=message_id,
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role="tool",
                content=content,
                category=category.value,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                sequence_number=seq if persist_data.should_persist else 0,
                status="completed",
                metadata=metadata,
                channels={"sse"},
                message_id=message_id,
                action="update",
            )

        return MessageHandlerResult(
            category=category.value,
            persisted=persist_data.should_persist,
            streamed=stream_data.should_stream,
            message_id=message_id,
            sequence_number=seq,
        )

    async def handle_tool_error(
        self,
        tool_name: str,
        error: BaseException,
        tool_call_id: str | None = None,
        sequence_number: int | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        """处理工具执行错误 — 将 running 记录标记为 failed"""
        content = str(error) if error else "Tool execution failed"
        seq = sequence_number or 0

        # Rebuild metadata even on error to keep UI consistent
        metadata_registry = get_tool_metadata(tool_name)
        input_data = await self._repository.resolve_tool_input(
            tool_call_id, tool_name=tool_name
        )
        display_name = None
        if metadata_registry.summary_template and input_data:
            display_name = metadata_registry.get_display_name(tool_name, input_data)

        metadata = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": input_data,
            "error": content,
            "tool_meta": {"display_name": display_name},
        }

        message_id = None
        if sequence_number:
            update_result = await self._repository.update(
                sequence_number=sequence_number,
                status="failed",
                content=content,
                node_source=node_source,
                meta_data=metadata,
            )
            if update_result:
                message_id = update_result if isinstance(update_result, str) else None

        return MessageHandlerResult(
            category="tool_error",
            persisted=bool(sequence_number),
            streamed=False,
            message_id=message_id,
            sequence_number=seq,
        )

    async def handle_user_message(
        self, content: str, metadata: dict | None = None
    ) -> MessageHandlerResult:
        """处理用户消息"""
        category = MessageCategory.USER
        message_id, seq = await self._repository.persist(
            role="human",
            content=content,
            category=category.value,
            is_visible=True,
            content_type="text",
            metadata=metadata,
            parent_id=None,  # User message parent is resolved in repository if None
        )
        await self._dispatch_block(
            role="human",
            content=content,
            category=category.value,
            sequence_number=seq,
            channels={"sse"},
        )
        return MessageHandlerResult(
            category=category.value,
            persisted=True,
            streamed=True,
            message_id=message_id,
            sequence_number=seq,
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
        metadata: dict | None = None,
    ) -> MessageHandlerResult:
        """处理人机交互请求（HITL）"""
        logger.info(
            f"[MessageHandler] Handling HITL request: {request_id} (tool={tool_name})"
        )
        content = json.dumps(
            {
                "id": request_id,
                "type": request_type,
                "prompt": prompt,
                "options": options,
                "context": context,
                "default_value": default_value,
            },
            ensure_ascii=False,
        )

        # Generate tool_meta if tool information is provided
        final_metadata = dict(metadata) if metadata else {}
        final_metadata["hitl_request_id"] = request_id
        if tool_name:
            from app.core.tools.registry import get_tool_metadata

            tool_meta = get_tool_metadata(tool_name)
            if tool_meta and tool_meta.summary_template:
                final_metadata["tool_meta"] = {
                    "name": tool_name,
                    "display_name": tool_meta.get_display_name(
                        tool_name, {"request_type": request_type, "prompt": prompt}
                    ),
                }

        effective_parent_id = parent_id or await self._repository.get_last_message_id()

        dev_key, dev_name = self._get_device_attribution()
        message_id, seq = await self._repository.persist(
            role="system",
            content=content,
            category=MessageCategory.HITL_REQUEST.value,
            action_type="human_request",
            status="waiting_human",
            is_visible=True,
            content_type="json",
            tool_call_id=tool_call_id or request_id,  # Fallback to request_id
            tool_name=tool_name,
            metadata=final_metadata if final_metadata else None,
            parent_id=effective_parent_id,
            executor_device_key=dev_key,
            executor_device_name=dev_name,
        )
        await self._dispatch_block(
            role="system",
            content=content,
            category=MessageCategory.HITL_REQUEST.value,
            status="waiting_human",
            sequence_number=seq,
            tool_name=tool_name,
            tool_call_id=tool_call_id or request_id,
            metadata=final_metadata if final_metadata else None,
            channels={"sse"},
            parent_id=effective_parent_id,
        )

        # Mobile 通道：发送 hitl.request 规范信封（直接构造，不经 _publish_mobile）
        if not self._publisher:
            self._publisher = MessagePublisher(
                thread_id=self.thread_id, project_id=self.project_id
            )
        await self._publisher.publish_hitl_request(
            request_id=request_id,
            request_type=request_type,
            prompt=prompt,
            options=options,
            context=context,
            default_value=default_value,
            tool_name=tool_name,
            metadata=final_metadata if final_metadata else None,
        )

        return MessageHandlerResult(
            category=MessageCategory.HITL_REQUEST.value,
            persisted=True,
            streamed=True,
            message_id=message_id,
        )

    async def handle_error(self, error: Exception) -> MessageHandlerResult:
        """处理异常上报"""
        from app.core.engine.error_handler import LLMErrorHandler

        classification = LLMErrorHandler.classify_exception(error)
        category = (
            MessageCategory.ERROR_BUSINESS
            if classification.error_type in ["business_logic", "workflow_error"]
            else MessageCategory.ERROR_SYSTEM
        )

        logger.warning(
            f"[MessageHandler] Handling error: {classification.error_type} (cat={category.value})"
        )

        message_id = None
        if category == MessageCategory.ERROR_BUSINESS:
            error_markdown = f"**{classification.title}**\n\n{classification.message}\n\n*Hint: {classification.hint}*"
            dev_key, dev_name = self._get_device_attribution()
            message_id, _ = await self._repository.persist(
                role="ai",
                content=error_markdown,
                category=category.value,
                is_visible=True,
                content_type="markdown",
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )

        from app.core.engine.message.mobile_notifier import MobileErrorNotifier

        await MobileErrorNotifier(self).push(classification)

        if classification.error_type == "quota_exhausted":
            if not self._publisher:
                self._publisher = MessagePublisher(
                    thread_id=self.thread_id, project_id=self.project_id
                )
            await self._publisher.publish(
                QuotaExhaustedEvent(
                    thread_id=self.thread_id,
                    title=classification.title,
                    message=classification.message,
                    hint=classification.hint,
                )
            )

        elif classification.error_type == "llm_auth":
            if not self._publisher:
                self._publisher = MessagePublisher(
                    thread_id=self.thread_id, project_id=self.project_id
                )
            await self._publisher.publish(
                LLMAuthErrorEvent(
                    thread_id=self.thread_id,
                    title=classification.title,
                    message=classification.message,
                )
            )

        # Terminal errors should appear in chat list like an AI message.
        # "system" role is filtered out by frontend _appendMessage.
        error_role = "ai" if classification.is_terminal else "system"
        await self._dispatch_block(
            role=error_role,
            content=f"**{classification.title}**\n{classification.message}",
            category=category.value,
            metadata={
                "error_type": classification.error_type,
                "hint": classification.hint,
                "is_terminal": classification.is_terminal,
            },
            channels={"sse"},
        )

        # [STATUS FIX] Ensure frontend transitions to error state
        if not self._publisher:
            self._publisher = MessagePublisher(
                thread_id=self.thread_id, project_id=self.project_id
            )
        # Only send generic error status for non-terminal errors.
        # Terminal errors (quota_exhausted, llm_auth) already sent dedicated events.
        if not classification.is_terminal:
            await self._publisher.publish(
                StatusEvent(thread_id=self.thread_id, status="error")
            )

        return MessageHandlerResult(
            category=category.value,
            persisted=category == MessageCategory.ERROR_BUSINESS,
            streamed=True,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_device_attribution(self) -> tuple[str | None, str | None]:
        """获取当前运行环境的 A2A 设备标识"""
        try:
            from app.core.config import settings
            from app.core.evocloud.manager import evocloud_manager

            dev_key = (
                evocloud_manager.link.device_key
                if (evocloud_manager and evocloud_manager.link)
                else None
            )
            dev_name = settings.EVOCLOUD_DEVICE_NAME
            return dev_key, dev_name
        except Exception:
            return None, None

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
        references: list | None = None,
        message_id: str | None = None,
        action: str = "create",
    ) -> None:
        """统一构造 MessageBlock 并分发"""
        if sequence_number == 0:
            self._stream_seq += 1
            sequence_number = self._stream_seq

        # Prune content for tool messages on SSE to save bandwidth as frontend doesn't need it
        dispatch_content = content or ""
        if role == "tool" and channels and "sse" in channels:
            dispatch_content = ""

        # Get device info for AI / Tool / System messages
        dev_key = None
        dev_name = None
        if role != "human":
            dev_key, dev_name = self._get_device_attribution()

        from app.core.engine.message.factory import MessageBlockFactory

        block = MessageBlockFactory.from_event(
            thread_id=self.thread_id,
            sequence_number=sequence_number,
            role=role,
            content=dispatch_content,
            thinking=thinking,
            tool_calls=tool_calls,
            category=category,
            status=status,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            metadata=metadata,
            parent_id=parent_id,
            run_id=self.run_id,
            references=references,
            message_id=message_id,
            executor_device_key=dev_key,
            executor_device_name=dev_name,
        )

        if not self._publisher:
            self._publisher = MessagePublisher(
                thread_id=self.thread_id, project_id=self.project_id
            )

        await self._publisher.publish(block, channels=channels, action=action)

    @staticmethod
    async def stream_token(
        thread_id: str, token_buffer: str, message_id: str | None = None
    ) -> None:
        """分发 LLM Token 片段"""
        if not token_buffer:
            return
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(
            TokenEvent(thread_id=thread_id, content=token_buffer, message_id=message_id)
        )

    @staticmethod
    async def stream_thinking(
        thread_id: str, thinking_delta: str, message_id: str | None = None
    ) -> None:
        """分发 AI 思考过程片段"""
        if not thinking_delta:
            return
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(
            ThinkingEvent(
                thread_id=thread_id, content=thinking_delta, message_id=message_id
            )
        )

    @staticmethod
    async def stream_progress(
        thread_id: str,
        message: str,
        progress: int | None = None,
        status: str = "running",
        metadata: dict | None = None,
    ) -> None:
        """分发任务/工具执行进度"""
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(
            ProgressEvent(
                thread_id=thread_id,
                status=status,  # type: ignore
                message=message,
                progress=progress,
                metadata=metadata or {},
            )
        )
