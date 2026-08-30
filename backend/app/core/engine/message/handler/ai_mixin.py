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
        node_source: str | None = None,
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

        is_visible = category.is_visible_to_user and not _is_finish_message

        if persist_data.should_persist:
            from app.core.engine.message.extractor import attachment_extractor

            extracted_refs = attachment_extractor.extract_from_ai_response(content=persist_data.content)

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
                node_source=node_source,
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
                    # channels decided by OutputChannelPolicy (node_source ContextVar)
                    parent_id=effective_parent_id,
                    message_id=msg_id,
                    is_visible=is_visible,
                )

        if stream_data.should_stream and not _is_finish_message:
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
                # channels decided by OutputChannelPolicy (node_source ContextVar)
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
