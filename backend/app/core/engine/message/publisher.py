"""
MessagePublisher —— 统一消息分发器。

职责：
1. 将 MessageBlock 分发到所有前端通道（SSE + Mobile + 内部事件总线）
2. 屏蔽底层传输细节（Pub/Sub / WebSocket / EvoCloud）
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
from app.models.schemas.events import BaseStreamEvent
from app.infrastructure.pydantic_base import EventBase
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


class MessagePublisher:
    """统一消息分发器：MessageBlock → SSE + Mobile + 内部事件总线"""

    def __init__(self, thread_id: str, project_id: int | None = None):
        self.thread_id = thread_id
        self.project_id = project_id

    async def publish(
        self, 
        payload: MessageBlock | BaseStreamEvent | EventBase, 
        channels: set[str] | None = None, 
        action: str = "create"
    ) -> None:
        """
        统一分发入口：将数据（块或流）分发到注册的前端通道。

        Args:
            payload: MessageBlock (持久化消息块) 或 BaseStreamEvent (标准化流式事件)
            channels: 指定通道，默认根据 payload 类型自动决定
            action: 仅针对 MessageBlock 的 SSE 动作 (create/update/append)
        """
        if channels is None:
            # 默认：MessageBlock 发往双端，BaseStreamEvent 仅发往 SSE
            channels = {"sse", "mobile"} if isinstance(payload, MessageBlock) else {"sse"}

        if "sse" in channels:
            await self._send_to_sse(payload, action=action)

        if "mobile" in channels and isinstance(payload, MessageBlock):
            await self._publish_mobile(payload)

    async def _send_to_sse(self, payload: MessageBlock | BaseStreamEvent, action: str = "create") -> None:
        """推送数据到 Web UI (SSE)"""
        try:
            channel = f"chat:{self.thread_id}:events"
            
            if isinstance(payload, MessageBlock):
                event = BlockMapper.to_sse(payload, action=action)
                data_json = event.model_dump_json()
            elif isinstance(payload, BaseStreamEvent):
                # 调用统一的平铺序列化逻辑
                data_json = payload.to_json()
            elif hasattr(payload, "model_dump_json"):
                data_json = payload.model_dump_json(exclude_none=True)
            else:
                data_json = str(payload)

            bus = get_event_bus()
            await bus.publish(channel, data_json)
            # logger.debug(f"[Publisher] SSE sent: type={getattr(payload, 'type', 'message')}")

        except Exception as e:
            logger.warning(f"[Publisher] SSE send failed: {e}")

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
        """推送系统错误消息（复用 publish 入口）"""
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
            meta_data={
                "title": title,
                "error_type": error_type,
                **(metadata or {}),
            },
        )
        await self.publish(block)
