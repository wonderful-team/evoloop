import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.constants import (
    MessageContentType,
    MessageRole,
    MessageStatus,
)
from app.core.engine.message.persistence import MessagePersistencePolicy
from app.core.engine.message.schemas import MessageHandlerResult
from app.core.engine.message.stream import MessageStreamPolicy

logger = logging.getLogger(__name__)


class AiMessageMixin:
    async def handle_ai_message(
        self,
        content: str,
        tool_calls: list | None = None,
        thinking: str | None = None,
        metadata: dict | None = None,
        parent_id: str | None = None,
        message_id: str | None = None,
        extra_references: list[dict] | None = None,
    ) -> MessageHandlerResult:
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

        is_visible = category.is_visible_to_user

        if persist_data.should_persist:
            from app.core.engine.message.extractor import attachment_extractor

            extracted_refs = attachment_extractor.extract_from_ai_response(content=persist_data.content)

            # 结构化媒体引用直传（工具生成图/视频时经 ctx 暂存）：
            # 不依赖模型在正文中复述链接，合并去重后落库为 references。
            if extra_references:
                seen = {r.get("target_id") for r in extracted_refs if isinstance(r, dict)}
                for ref in extra_references:
                    if isinstance(ref, dict) and ref.get("target_id") not in seen:
                        extracted_refs.append(ref)
                        seen.add(ref.get("target_id"))

            dev_key, dev_name = self._get_device_attribution()
            msg_id, seq = await self._repository.persist(
                role=MessageRole.AI,
                content=persist_data.content,
                thinking=persist_data.thinking,
                tool_calls=persist_data.tool_calls,
                category=category.value,
                is_visible=is_visible,
                content_type=MessageContentType.TEXT,
                metadata=metadata,
                parent_id=effective_parent_id,
                references=extracted_refs,
                message_id=msg_id,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )

            if msg_id and is_visible and category != MessageCategory.INTERNAL_REASONING:
                await self._dispatch_block(
                    role=MessageRole.AI,
                    content=persist_data.content,
                    thinking=persist_data.thinking,
                    tool_calls=persist_data.tool_calls,
                    category=category.value,
                    status=MessageStatus.COMPLETED,
                    sequence_number=seq,
                    parent_id=effective_parent_id,
                    message_id=msg_id,
                    is_visible=is_visible,
                    references=extracted_refs,
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role=MessageRole.AI,
                content=stream_data.content,
                category=category.value,
                metadata=metadata,
                tool_calls=persist_data.tool_calls,
                thinking=thinking,
                sequence_number=seq if persist_data.should_persist else 0,
                status=MessageStatus.STREAMING if persist_data.should_persist else MessageStatus.COMPLETED,
                references=extracted_refs if persist_data.should_persist else None,
                parent_id=effective_parent_id,
                message_id=msg_id,
                is_visible=is_visible,
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
