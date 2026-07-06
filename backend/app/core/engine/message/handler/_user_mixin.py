import json
import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.schemas import MessageHandlerResult

logger = logging.getLogger(__name__)


class UserMessageMixin:
    async def handle_user_message(
        self, content: str, metadata: dict | None = None
    ) -> MessageHandlerResult:
        category = MessageCategory.USER
        message_id, seq = await self._repository.persist(
            role="human",
            content=content,
            category=category.value,
            is_visible=True,
            content_type="text",
            metadata=metadata,
            parent_id=None,
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
            tool_call_id=tool_call_id or request_id,
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
