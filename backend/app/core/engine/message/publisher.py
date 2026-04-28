"""
MessagePublisher —— 统一消息分发器。

职责：
1. 将 MessageBlock 分发到所有前端通道（SSE + Mobile + 内部事件总线）
2. 屏蔽底层传输细节（Redis Pub/Sub / WebSocket / EvoCloud）
3. 支持消息去重和批量缓冲

使用示例：
    from app.core.engine.message.schemas import MessageBlock
    from app.core.engine.message.mapper import BlockMapper
    from app.core.engine.message.publisher import MessagePublisher

    block = BlockMapper.from_db(db_msg)
    publisher = MessagePublisher(thread_id="xxx")
    await publisher.publish(block)
"""

import logging
import time
from datetime import datetime
from typing import Any

from app.core.engine.message.event_bus import get_event_bus
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


class MessagePublisher:
    """统一消息分发器：MessageBlock → SSE + Mobile + 内部事件总线"""

    def __init__(self, thread_id: str, project_id: int | None = None):
        self.thread_id = thread_id
        self.project_id = project_id

    async def publish(self, block: MessageBlock, channels: set[str] | None = None, action: str = "create") -> None:
        """
        将 MessageBlock 分发到所有注册的前端通道。

        Args:
            block: 标准化的消息块
            channels: 指定通道，默认 {"sse", "mobile"}
            action: SSE 事件动作类型 (create/update/append)
        """
        channels = channels or {"sse", "mobile"}

        if "sse" in channels:
            await self._publish_sse(block, action=action)

        if "mobile" in channels:
            await self._publish_mobile(block)

    async def _publish_sse(self, block: MessageBlock, action: str = "create") -> None:
        """通过 EventBus 推送到 Web UI (SSE)"""
        try:
            event = BlockMapper.to_sse(block, action=action)
            channel = f"chat:{self.thread_id}:events"
            payload = event.model_dump_json()

            bus = get_event_bus()
            await bus.publish(channel, payload)
            logger.debug(f"[Publisher] SSE published: seq={block.sequence_number}, role={block.role}, action={action}")

        except Exception as e:
            logger.warning(f"[Publisher] SSE publish failed: {e}")

    async def _publish_mobile(self, block: MessageBlock) -> None:
        """通过 EvoCloud Gateway WebSocket 推送到 Mobile"""
        try:
            if not evocloud_manager.link or not evocloud_manager.link.is_connected():
                logger.debug("[Publisher] WebSocket not connected, skipping mobile push")
                return

            # 跳过对人类消息的推送（Mobile 已做乐观更新）
            if block.role == "human":
                return

            # 跳过对用户不可见的内部消息
            if not block.is_visible:
                return

            mobile_data = BlockMapper.to_mobile(block)
            await evocloud_manager.link.send_message({
                "type": "message_sync",
                "data": mobile_data,
            })
            logger.debug(f"[Publisher] Mobile published: seq={block.sequence_number}, role={block.role}")

        except Exception as e:
            logger.warning(f"[Publisher] Mobile publish failed: {e}")

    async def publish_error(
        self,
        title: str,
        message: str,
        error_type: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        推送错误消息到所有通道。

        用于非消息流场景（如配额耗尽、认证过期等系统级错误）。
        """
        try:
            block = MessageBlock(
                id=f"msg-{self.thread_id}-error-{int(time.time() * 1000)}",
                thread_id=self.thread_id,
                role="system",
                category="error_system",
                content=message,
                content_type="text",
                status="failed",
                is_visible=True,
                created_at=datetime.now().isoformat(),
                metadata={
                    "title": title,
                    "error_type": error_type,
                    **(metadata or {}),
                },
            )

            event = BlockMapper.to_sse(block)
            await self.publish(block, channels={"sse", "mobile"})
            logger.info(f"[Publisher] Error published: {error_type}")

        except Exception as e:
            logger.warning(f"[Publisher] Error publish failed: {e}")
