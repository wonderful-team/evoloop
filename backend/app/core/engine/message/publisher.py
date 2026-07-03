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

import json
import logging
from datetime import datetime
from typing import Any

from app.core.schemas.canonical import MessageType, create_envelope

from app.core.config import settings
from app.core.engine.message.event_bus import get_event_bus
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.core.evocloud import evocloud_manager
from app.infrastructure.pydantic_base import EventBase
from app.models.schemas.events import BaseStreamEvent

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
        except Exception as e:
            logger.warning(f"[Publisher] SSE send failed: {e}")

    async def publish_custom_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish a custom structured event to the chat SSE channel."""
        try:
            payload = {
                "type": event_type,
                "data": data,
                "thread_id": self.thread_id,
                "project_id": self.project_id,
            }
            bus = get_event_bus()
            await bus.publish(f"chat:{self.thread_id}:events", json.dumps(payload))
            logger.debug(f"[Publisher] Published custom event {event_type} for thread {self.thread_id}")
        except Exception as e:
            logger.warning(f"[Publisher] Custom event publish failed: {e}")

    async def _publish_mobile(self, block: MessageBlock) -> None:
        """通过 EvoCloud Gateway WebSocket 推送到 Mobile，WS 失败时入队 Huey 由 Worker 异步兜底 HTTP。"""
        if not settings.MOBILE_SYNC_ENABLED:
            return

        # 回环防护由上层根据 device_key / client_id / source 判断，不在此处过滤。
        if block.role == "human" and not block.is_visible:
            return

        mobile_data = BlockMapper.to_mobile(block)
        sync_env = create_envelope(
            type=MessageType.MESSAGE_SYNC,
            body=mobile_data,
            target={"kind": "mobile"},
        )

        link = evocloud_manager.link
        if link and link.is_connected():
            try:
                ok = await link.send_message(sync_env.model_dump())
                if ok is not False:  # send_message 返回 True 或 None
                    logger.debug(f"[Publisher] Mobile WS published: seq={block.sequence_number}, role={block.role}")
                    return
            except Exception as e:
                logger.warning(f"[Publisher] WS send failed, enqueuing Huey task: {e}")
        else:
            logger.debug("[Publisher] WS not connected, enqueuing Huey task")

        # WS 不可达 → 异步入队 Huey，Worker 进程负责 HTTP→MC（带重试）
        from app.core.engine.message.tasks import mobile_sync_http_task
        mobile_sync_http_task.delay(mobile_data)

    async def publish_error(
        self,
        title: str,
        message: str,
        error_type: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """推送系统错误消息（复用 publish 入口）"""
        import uuid
        block = MessageBlock(
            id=str(uuid.uuid4()),
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

    async def publish_hitl_request(
        self,
        request_id: str,
        request_type: str,
        prompt: str,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """向 Mobile 推送 hitl.request 规范信封。

        替代旧的 _publish_mobile(block) -> message.sync 路径。
        HITL 需要 WS 在线，无法异步兜底。
        """
        if not settings.MOBILE_SYNC_ENABLED:
            return

        hitl_body: dict[str, Any] = {
            "request_id": request_id,
            "request_type": request_type,
            "prompt": prompt,
        }
        if options is not None:
            hitl_body["options"] = options
        if context is not None:
            hitl_body["context"] = context
        if default_value is not None:
            hitl_body["default_value"] = default_value
        if tool_name is not None:
            hitl_body["tool_name"] = tool_name
        if metadata is not None:
            hitl_body["metadata"] = metadata

        hitl_env = create_envelope(
            type=MessageType.HITL_REQUEST,
            body=hitl_body,
            target={"kind": "mobile"},
        )

        link = evocloud_manager.link
        if link and link.is_connected():
            try:
                ok = await link.send_message(hitl_env.model_dump())
                if ok is not False:
                    logger.info(
                        f"[Publisher] hitl.request sent to Mobile: "
                        f"req_id={request_id}, type={request_type}"
                    )
                    return
            except Exception as e:
                logger.warning(f"[Publisher] hitl.request WS send failed: {e}")
        else:
            logger.warning(
                f"[Publisher] WS not connected, hitl.request CANNOT reach Mobile: req_id={request_id}"
            )
