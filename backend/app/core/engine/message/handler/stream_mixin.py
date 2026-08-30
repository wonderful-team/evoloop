from typing import Any, cast

from app.core.engine.message.constants import MessageStatus
from app.core.engine.message.publisher import MessagePublisher
from app.models.schemas.events import (
    ProgressEvent,
    ThinkingEvent,
    TokenEvent,
)


class StreamMixin:
    @staticmethod
    async def stream_token(
        thread_id: str, token_buffer: str, message_id: str | None = None
    ) -> None:
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
        status: str = MessageStatus.RUNNING,
        metadata: dict | None = None,
    ) -> None:
        publisher = MessagePublisher(thread_id=thread_id)
        await publisher.publish(
            ProgressEvent(
                thread_id=thread_id,
                status=cast(Any, status),
                message=message,
                progress=progress,
                metadata=metadata or {},
            )
        )
