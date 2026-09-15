import json
import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.constants import (
    MessageContentType,
    MessageRole,
    MessageStatus,
)
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.schemas import MessageHandlerResult
from app.core.hitl.constants import MESSAGE_ACTION_TYPE_HUMAN_REQUEST

logger = logging.getLogger(__name__)


class UserMessageMixin:
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
        suppress_user_push: bool = False,
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
            role=MessageRole.SYSTEM,
            content=content,
            category=MessageCategory.HITL_REQUEST.value,
            action_type=MESSAGE_ACTION_TYPE_HUMAN_REQUEST,
            status=MessageStatus.WAITING_HUMAN,
            is_visible=True,
            content_type=MessageContentType.JSON,
            tool_call_id=tool_call_id or request_id,
            tool_name=tool_name,
            metadata=final_metadata if final_metadata else None,
            parent_id=effective_parent_id,
            executor_device_key=dev_key,
            executor_device_name=dev_name,
        )
        if not suppress_user_push:
            # 通道决策：默认 SSE-only（HITL 交互 UI 在 Web，移动端尚无作答界面）。
            # 值守（duty）例外：提问必须实时触达负责人手机（移动端看到通知后
            # 到 Web 作答）——否则值守信任纪律中"应答要快"没有投递通道。
            from app.core.channel.duty import is_duty_source
            from app.core.context.manager import ContextManager

            ctx = ContextManager.current()
            source = str((ctx.metadata or {}).get("source") or "") if ctx else ""
            channels = {"sse", "mobile"} if is_duty_source(source) else {"sse"}
            await self._dispatch_block(
                role=MessageRole.SYSTEM,
                content=content,
                category=MessageCategory.HITL_REQUEST.value,
                status=MessageStatus.WAITING_HUMAN,
                sequence_number=seq,
                tool_name=tool_name,
                tool_call_id=tool_call_id or request_id,
                metadata=final_metadata if final_metadata else None,
                channels=channels,
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
            streamed=not suppress_user_push,
            message_id=message_id,
        )
