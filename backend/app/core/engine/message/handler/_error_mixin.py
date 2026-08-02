import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.schemas import MessageHandlerResult
from app.models.schemas.events import (
    LLMAuthErrorEvent,
    QuotaExhaustedEvent,
    StatusEvent,
)

logger = logging.getLogger(__name__)


class ErrorMessageMixin:
    async def handle_error(self, error: Exception) -> MessageHandlerResult:
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
            # SSE-only: error messages are web-chat notifications. The mobile
            # error path is handled by MobileErrorNotifier separately.
            channels={"sse"},
        )

        if not self._publisher:
            self._publisher = MessagePublisher(
                thread_id=self.thread_id, project_id=self.project_id
            )
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
