"""
MobileChannel — pushes messages to Mobile via Gateway HTTP API.

Architecture:
    Desktop Agent --HTTP POST /api/v1/message/send--> Gateway --WS--> Mobile

Channel 抽象统一了所有出站路径，传输层通过 HTTP 调用 Gateway。
"""

import logging
from typing import Any

from app.core.config import settings
from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from app.core.evocloud import evocloud_manager
from app.core.schemas.canonical import MessageType, create_envelope

from ..base import Channel, ChannelContext

logger = logging.getLogger(__name__)


class MobileChannel(Channel):
    """Relays messages to Mobile via Gateway HTTP API."""

    name = "mobile"
    accepts_blocks = True
    accepts_stream_events = False

    async def _send_via_http(self, env_type: str, body: dict[str, Any], target_device_key: str = "") -> bool:
        """Send a canonical envelope via HTTP POST /api/v1/message/send."""
        env = create_envelope(type=env_type, body=body, target={"kind": "mobile"})
        payload = {"target_device_key": target_device_key, "envelope": env.model_dump()}
        try:
            resp = await evocloud_manager.api.request("POST", "/api/v1/message/send", data=payload)
            code = resp.get("code", -1) if isinstance(resp, dict) else -1
            return code == 0
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
            logger.warning("[MobileChannel] HTTP send failed: %s", e)
            return False

    async def send(
        self,
        payload: MessageBlock | Any,
        ctx: ChannelContext,
    ) -> None:
        """Push a MessageBlock to mobile via Gateway HTTP API."""
        if not settings.MOBILE_SYNC_ENABLED:
            return
        if not isinstance(payload, MessageBlock):
            return
        block = payload
        if block.role == "human" and not block.is_visible:
            return

        device_key = await self._get_device_key()
        mobile_data = BlockMapper.to_mobile(block)

        sync_body = {
            "device_key": device_key,
            "thread_id": block.thread_id or "",
            "messages": [mobile_data],
            "conversation": {
                "id": block.thread_id or "",
                "title": block.thread_id or "新同步会话",
                "project_id": ctx.project_id or 0,
            },
        }
        mobile_data.pop("device_key", None)

        ok = await self._send_via_http(MessageType.MESSAGE_SYNC, sync_body)
        if ok:
            logger.debug("[MobileChannel] HTTP published: seq=%s, role=%s", block.sequence_number, block.role)
        else:
            logger.warning("[MobileChannel] HTTP send failed, enqueuing Huey task")
            from app.core.engine.message.tasks import mobile_sync_http_task
            mobile_sync_http_task.delay(mobile_data)

    async def _get_device_key(self) -> str:
        """Get the device key from identity service."""
        try:
            from app.core.identity import identity_service
            return await identity_service.store.get_device_key() or ""
        except Exception:
            return ""

    async def send_envelope(
        self,
        env_type: str,
        body: dict[str, Any],
        target_device_key: str | None = None,
        member_id: int = 0,
    ) -> None:
        """Send an arbitrary canonical envelope to Gateway via HTTP."""
        if not settings.MOBILE_SYNC_ENABLED:
            return
        ok = await self._send_via_http(env_type, body, target_device_key or "")
        if ok:
            logger.debug("[MobileChannel] Envelope sent via HTTP: type=%s", env_type)
        else:
            logger.warning("[MobileChannel] Envelope send FAILED via HTTP: type=%s", env_type)

    async def send_hitl_request(
        self,
        request_id: str,
        request_type: str,
        prompt: str,
        ctx: ChannelContext,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Push a hitl.request to Mobile via Gateway HTTP API."""
        if not settings.MOBILE_SYNC_ENABLED:
            return
        hitl_body: dict[str, Any] = {"request_id": request_id, "request_type": request_type, "prompt": prompt}
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
        ok = await self._send_via_http(MessageType.HITL_REQUEST, hitl_body)
        if ok:
            logger.info("[MobileChannel] hitl.request sent via HTTP: req_id=%s", request_id)
        else:
            logger.warning("[MobileChannel] hitl.request send FAILED via HTTP: req_id=%s", request_id)
