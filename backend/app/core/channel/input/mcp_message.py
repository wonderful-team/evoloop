"""McpMessageChannel — 通用第三方 MCP 消息渠道（入站归一化 + 出站回复）。

入站：第三方系统以 MCP server 接入，推送 notification，method 统一为
``notifications/mcp_message_send``，payload 即消息本体 + 可选建任务参数
（push 语义；幂等由推送方 event_id + domain 摄取层 dedup_key 共同保证）::

    {
        "event_id": "evt-1",              # 必填：幂等键
        "title": "处理订单退款",           # 必填：任务标题
        "project_id": 1,                  # 可选：缺省 0（派发前归属解析回填）
        "content": "订单 #123 已支付...",  # 可选：消息正文 → 任务描述
        "contact": "wxid_xxx",            # 可选：会话类消息的回复路由目标
        "category": "trade",              # 可选：任务分类
        "priority": "high",               # 可选：low/medium/high
        "risk_level": "T2",               # 可选：T1-T4
        "start_in_hours": 2               # 可选：延时派发（小时）
    }

出站：任务回复经 OutboundReplyEvent（domain 决策）路由到本渠道，
调用来源 server 上的 ``mcp_message_reply`` 工具发送（超长分块）::

    mcp_message_reply(contact="wxid_xxx", content="...", project_id=1)

入站通知的传输形态：MCP 客户端 SDK 对未知 notification method 会做
联合类型校验并拒绝分发（自定义 method 不可达），因此统一走 MCP 标准的
logging 通知 ``notifications/message``，消息本体放在 ``params.data`` 中，
``data.type = "mcp_message_send"`` 作为本通道的识别标记。

职责边界：本渠道只做「传输」（归一化入站 / 发送出站），
不含任何队列/业务语义（校验、幂等、状态机、回复路由决策在 domain/tasks）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.events import system_bus
from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import (
    InboundMessageEvent,
    OutboundReplyEvent,
    SystemEventType,
)

logger = logging.getLogger(__name__)

# MCP 标准 logging 通知（notifications/message）是客户端 SDK 唯一允许
# 任意自定义载荷的 server→client 推送通道；本通道消息以
# params.data.type == MCP_MESSAGE_SEND_TYPE 识别。
LOGGING_NOTIFY_METHOD = "notifications/message"
MCP_MESSAGE_SEND_TYPE = "mcp_message_send"
REPLY_TOOL_NAME = "mcp_message_reply"
REPLY_TOOL_TIMEOUT_SECONDS = 10.0
# 商城微信客服单条消息长度上限（复用 GUI 线实测值，取安全余量）
MAX_MESSAGE_LEN = 1500
# 分块发送间隔（秒）：避开远程 server 限频
REPLY_CHUNK_DELAY_SECONDS = 0.5


@event_register()
class McpMessageChannel:
    """第三方 MCP 消息渠道：入站归一化 + 出站回复（单例，见模块尾）。"""

    name = "mcp_message"

    # ── 入站 ─────────────────────────────────────────────

    @event_subscribe(SystemEventType.MCP_SERVER_NOTIFICATION)
    async def on_server_notification(self, event: BaseEvent) -> None:
        server_name = str(getattr(event, "server_name", "") or "")
        method = str(getattr(event, "method", "") or "")
        if method != LOGGING_NOTIFY_METHOD:
            return

        # manager.py 把通知参数放在 event.data.payload（= notifications/message
        # 的 params）。SDK 强类型路径下 params 是 pydantic 模型
        # （LoggingMessageNotificationParams，.data 属性），宽松路径下是 dict。
        # 消息本体在 params.data，data.type == mcp_message_send 为识别标记。
        data = getattr(event, "data", None)
        wrapper = getattr(data, "payload", None)
        if wrapper is None:
            return
        message = wrapper.get("data") if isinstance(wrapper, dict) else getattr(wrapper, "data", None)
        if not isinstance(message, dict) or message.get("type") != MCP_MESSAGE_SEND_TYPE:
            return
        await self._publish_inbound(server_name, message)

    async def _publish_inbound(self, server_name: str, params: dict) -> bool:
        """归一化一条第三方消息并发布 InboundMessageEvent（push 入口）。

        返回是否真正发布（守卫拦截 = False）。外部输入边界：数值字段格式
        非法（如 project_id="abc"）→ warning + 丢弃该条消息（不向事件总线
        抛异常，一条坏消息不能污染整批采集）。
        """
        event_id = str(params.get("event_id") or "").strip()
        title = str(params.get("title") or "").strip()
        if not event_id or not title:
            logger.warning(
                "[mcp_message] message missing event_id/title, skipped (server=%s)",
                server_name,
            )
            return False

        try:
            project_id = int(params.get("project_id") or 0)
            start_in_hours = _optional_float(params.get("start_in_hours"))
        except (TypeError, ValueError) as e:
            logger.warning(
                "[mcp_message] malformed numeric field, skipped (server=%s, event=%s): %s",
                server_name,
                event_id,
                e,
            )
            return False

        await system_bus.publish(InboundMessageEvent(
            source=f"channel.{self.name}",
            source_system=server_name,
            event_id=event_id,
            project_id=project_id,
            title=title,
            content=str(params.get("content") or ""),
            contact=_optional_str(params.get("contact")),
            channel=self.name,
            category=_optional_str(params.get("category")),
            priority=str(params.get("priority") or "medium"),
            risk_level=_optional_str(params.get("risk_level")),
            start_in_hours=start_in_hours,
        ))
        logger.info(
            "[mcp_message] inbound message normalized (server=%s, event=%s)",
            server_name,
            event_id,
        )
        return True

    # ── 出站 ─────────────────────────────────────────────

    @event_subscribe(SystemEventType.OUTBOUND_REPLY)
    async def on_outbound_reply(self, event: OutboundReplyEvent) -> None:
        """发送路由到本渠道的任务回复（调来源 server 的 mcp_message_reply 工具，超长分块）。"""
        if event.channel != self.name:
            return
        server = event.source_system
        if not server:
            logger.warning(
                "[mcp_message] reply missing source_system, skipped (contact=%s)",
                event.recipient,
            )
            return

        chunks = _chunk_text(event.content, MAX_MESSAGE_LEN)
        sent_all = True
        for idx, chunk in enumerate(chunks):
            result = await self._call_tool(
                server,
                REPLY_TOOL_NAME,
                timeout=REPLY_TOOL_TIMEOUT_SECONDS,
                contact=event.recipient,
                content=chunk,
                project_id=event.project_id,
            )
            if not bool((result or {}).get("success")):
                sent_all = False
            if idx < len(chunks) - 1:
                await asyncio.sleep(REPLY_CHUNK_DELAY_SECONDS)
        logger.info(
            "[mcp_message] reply send %s | server=%s | contact=%s | chunks=%d | content=%r",
            "成功" if sent_all else "失败",
            server,
            event.recipient,
            len(chunks),
            event.content[:50],
        )

    async def _call_tool(self, server: str, tool_name: str, *, timeout: float, **kwargs) -> dict[str, Any]:
        """调用第三方 server 上的工具，解析 content[0].text 的 JSON。

        外部瞬时故障容忍但不静默：工具缺失 / 超时 / 失败一律 logger.warning
        并返回 {}（不向事件总线抛异常，阻塞值守）。
        """
        from app.core.mcp.client.manager import mcp_client_manager

        tools = await mcp_client_manager.get_tools(server)
        if not tools:
            logger.warning("[mcp_message] MCP server %s 未连接或无工具", server)
            return {}
        full_name = f"mcp__{server.replace('-', '_').lower()}__{tool_name}"
        tool = next((t for t in tools if t.name == full_name), None)
        if tool is None:
            logger.warning("[mcp_message] 工具 %s 不在 %s 上", full_name, server)
            return {}
        try:
            result = await asyncio.wait_for(tool.func(**kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "[mcp_message] 调用 %s 超时(>%ss)（外部 MCP 僵死不能阻塞值守）",
                full_name,
                timeout,
            )
            return {}
        except Exception as e:
            logger.warning(
                "[mcp_message] 调用 %s 失败: %s", full_name, e, exc_info=True
            )
            return {}
        return _parse_tool_result(result)


def _parse_tool_result(result: Any) -> dict[str, Any]:
    """把 CallToolResult 的 text content 解析为 dict；失败返回 {}。"""
    try:
        content = getattr(result, "content", None) or []
        for c in content:
            text = getattr(c, "text", None)
            if text:
                decoded = json.loads(text)
                if isinstance(decoded, dict):
                    return decoded
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("[mcp_message] 工具返回非 JSON，忽略: %r", result)
    return {}


def _chunk_text(text: str, max_len: int) -> list[str]:
    """按 max_len 切块（软切：优先在换行处断，避免词中截断）。"""
    text = text or ""
    if len(text) <= max_len:
        return [text] if text else []
    chunks: list[str] = []
    while text:
        piece = text[:max_len]
        if len(text) > max_len:
            cut = piece.rfind("\n")
            if cut > max_len // 2:
                piece = piece[:cut]
        chunks.append(piece)
        text = text[len(piece):].lstrip("\n")
    return chunks


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


# 单例：@event_register 在实例化时注册订阅者，非单例会重复注册（重复发送）。
mcp_message_channel = McpMessageChannel()
