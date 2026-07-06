import logging

from app.core.engine.message.publisher import MessagePublisher

logger = logging.getLogger(__name__)


class DispatchMixin:
    def _get_device_attribution(self) -> tuple[str | None, str | None]:
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
        except (ImportError, AttributeError):
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
        if sequence_number == 0:
            self._stream_seq += 1
            sequence_number = self._stream_seq

        dispatch_content = content or ""
        if role == "tool" and channels and "sse" in channels:
            dispatch_content = ""

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
