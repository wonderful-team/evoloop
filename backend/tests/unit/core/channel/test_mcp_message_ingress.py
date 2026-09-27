"""McpMessageChannel 单测：mcp_message 通知 → InboundMessageEvent 归一化。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.core.channel.input.mcp_message import (
    MAX_MESSAGE_LEN,
    mcp_message_channel,
)
from app.core.events.registry import InboundMessageEvent


def _notification(message: dict) -> SimpleNamespace:
    """模拟 manager.py 发布的真实 MCP 通知事件（notifications/message wrapper）。"""
    return SimpleNamespace(
        server_name="capability-matrix",
        method="notifications/message",
        data=SimpleNamespace(
            payload={"level": "info", "logger": "mcp_message", "data": {"type": "mcp_message_send", **message}},
        ),
    )


async def _capture_publish(monkeypatch) -> list[InboundMessageEvent]:
    captured: list[InboundMessageEvent] = []

    async def _fake_publish(event):
        captured.append(event)

    monkeypatch.setattr(
        "app.core.channel.input.mcp_message.system_bus", SimpleNamespace(publish=_fake_publish)
    )
    return captured


async def test_mcp_message_normalized(monkeypatch):
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({
                "event_id": "evt-1",
                "title": "处理订单退款",
                "content": "订单 #123 已支付",
                "project_id": 1,
                "contact": "wxid_abc",
                "category": "trade",
                "priority": "high",
                "risk_level": "T2",
                "start_in_hours": 2,
            },
        )
    )
    assert len(captured) == 1
    evt = captured[0]
    assert evt.source_system == "capability-matrix"
    assert evt.event_id == "evt-1"
    assert evt.title == "处理订单退款"
    assert evt.content == "订单 #123 已支付"
    assert evt.project_id == 1
    assert evt.contact == "wxid_abc"
    assert evt.category == "trade"
    assert evt.priority == "high"
    assert evt.risk_level == "T2"
    assert evt.start_in_hours == 2.0


async def test_other_methods_ignored(monkeypatch):
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    # logging 通知但识别标记不是 mcp_message_send（其他通道的消息）
    await sub.on_server_notification(
        _notification({"type": "kf_new_message", "event_id": "e-1", "title": "t"})
    )
    assert captured == []
    # 非 logging 通知 method（请求/响应类）不进入本通道
    await sub.on_server_notification(
        SimpleNamespace(
            server_name="capability-matrix",
            method="tools/call",
            data=SimpleNamespace(payload={}),
        )
    )
    assert captured == []


async def test_missing_event_id_or_title_skipped(monkeypatch):
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({"title": "no event id"})
    )
    await sub.on_server_notification(
        _notification({"event_id": "e-2"})
    )
    assert captured == []


async def test_optional_fields_default(monkeypatch):
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({"event_id": "e-3", "title": "minimal"})
    )
    assert len(captured) == 1
    evt = captured[0]
    assert evt.project_id == 0
    assert evt.content == ""
    assert evt.contact is None
    assert evt.channel == "mcp_message"
    assert evt.category is None
    assert evt.priority == "medium"
    assert evt.risk_level is None
    assert evt.start_in_hours is None


# ── 出站回复（OutboundReplyEvent → mcp_message_reply 工具调用）────────────


def _reply_event(**overrides):
    from app.core.events.registry import OutboundReplyEvent

    fields = {
        "channel": "mcp_message",
        "recipient": "wxid_abc",
        "content": "已处理完毕",
        "project_id": 1,
        "source_system": "capability-matrix",
        "thread_id": "wakeup_1_task-1",
    }
    fields.update(overrides)
    return OutboundReplyEvent(**fields)


class _FakeTool:
    def __init__(self, name: str, result=None, fail=False):
        self.name = name
        self.calls: list[dict] = []
        self._result = result
        self._fail = fail

    async def func(self, **kwargs):
        if self._fail:
            raise RuntimeError("boom")
        self.calls.append(kwargs)
        return self._result


async def _patch_tools(monkeypatch, tools):
    import app.core.mcp.client.manager as mgr_module

    class _FakeManager:
        async def get_tools(self, server_name=None):
            return tools

    monkeypatch.setattr(mgr_module, "mcp_client_manager", _FakeManager())


def _tool_result(payload: dict):
    return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])


async def test_outbound_reply_calls_mcp_reply_tool(monkeypatch):
    tool = _FakeTool(
        "mcp__capability_matrix__mcp_message_reply",
        result=_tool_result({"success": True}),
    )
    await _patch_tools(monkeypatch, [tool])
    sub = mcp_message_channel
    await sub.on_outbound_reply(_reply_event())
    assert len(tool.calls) == 1
    assert tool.calls[0]["contact"] == "wxid_abc"
    assert tool.calls[0]["content"] == "已处理完毕"
    assert tool.calls[0]["project_id"] == 1


async def test_outbound_reply_other_channel_ignored(monkeypatch):
    tool = _FakeTool("mcp__x__mcp_message_reply")
    await _patch_tools(monkeypatch, [tool])
    sub = mcp_message_channel
    await sub.on_outbound_reply(_reply_event(channel="wecom_duty"))
    assert tool.calls == []


async def test_outbound_reply_missing_server_skipped(monkeypatch):
    tool = _FakeTool("mcp__x__mcp_message_reply")
    await _patch_tools(monkeypatch, [tool])
    sub = mcp_message_channel
    await sub.on_outbound_reply(_reply_event(source_system=""))
    assert tool.calls == []


async def test_outbound_reply_tool_missing_tolerated(monkeypatch):
    await _patch_tools(monkeypatch, [_FakeTool("mcp__other__unrelated")])
    sub = mcp_message_channel
    await sub.on_outbound_reply(_reply_event())  # 不抛异常即通过


async def test_outbound_reply_tool_failure_tolerated(monkeypatch):
    tool = _FakeTool(
        "mcp__capability_matrix__mcp_message_reply", result=_tool_result({"success": True}), fail=True
    )
    await _patch_tools(monkeypatch, [tool])
    sub = mcp_message_channel
    await sub.on_outbound_reply(_reply_event())  # 异常被吞 + warning 日志，不抛
    assert tool.calls == []


# ── 输入健壮性（外部输入边界）──────────────────────────────


async def test_malformed_project_id_skipped(monkeypatch):
    """project_id 非数字 → warning + 丢弃该条（不向总线抛异常）"""
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({"event_id": "e-bad", "title": "t", "project_id": "abc"},
        )
    )
    assert captured == []


async def test_malformed_start_in_hours_skipped(monkeypatch):
    """start_in_hours 非数字 → 丢弃该条"""
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({"event_id": "e-bad2", "title": "t", "start_in_hours": "soon"},
        )
    )
    assert captured == []


async def test_start_in_hours_float_string_accepted(monkeypatch):
    """start_in_hours 数字字符串 → 正常转换"""
    captured = await _capture_publish(monkeypatch)
    sub = mcp_message_channel
    await sub.on_server_notification(
        _notification({"event_id": "e-f", "title": "t", "start_in_hours": "2.5"},
        )
    )
    assert len(captured) == 1
    assert captured[0].start_in_hours == 2.5


# ── 分块边界 ───────────────────────────────────────────────


async def test_reply_single_chunk_at_boundary(monkeypatch):
    """content 恰好等于上限 → 单块发送"""
    calls = await _patch_reply_tool(monkeypatch)
    await _send_reply("x" * MAX_MESSAGE_LEN)
    assert len(calls) == 1
    assert len(calls[0]["content"]) == MAX_MESSAGE_LEN


async def test_reply_newline_soft_cut(monkeypatch):
    """超长内容优先在换行处断，避免词中截断"""
    calls = await _patch_reply_tool(monkeypatch)
    head = "a" * 1400
    tail = "b" * 300
    await _send_reply(head + "\n" + tail)
    assert len(calls) == 2
    assert calls[0]["content"] == head  # 第一块在换行处截断
    assert calls[1]["content"] == tail  # 余部去掉换行后成块


async def test_reply_empty_content_no_call(monkeypatch):
    """空回复不发工具调用"""
    calls = await _patch_reply_tool(monkeypatch)
    await _send_reply("")
    assert calls == []


async def test_reply_partial_failure_attempts_all_chunks(monkeypatch):
    """某块失败不中断：其余块仍尝试，最终按失败上报"""
    tool = SimpleNamespace(name="mcp__capability_matrix__mcp_message_reply")
    calls: list[dict] = []

    async def _func(**kwargs):
        calls.append(kwargs)
        ok = len(calls) != 1  # 第一块失败
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({"success": ok}))]
        )

    tool.func = _func
    await _patch_tools(monkeypatch, [tool])
    monkeypatch.setattr(
        "app.core.channel.input.mcp_message.REPLY_CHUNK_DELAY_SECONDS", 0.0
    )
    await _send_reply("x" * (MAX_MESSAGE_LEN + 10))
    assert len(calls) == 2  # 两块都尝试了


# ── 复用 helper ────────────────────────────────────────────


async def _patch_reply_tool(monkeypatch) -> list[dict]:
    """注册一个记录调用的 mcp_message_reply 工具，返回 calls 列表（分块间隔归零）。"""
    tool = SimpleNamespace(name="mcp__capability_matrix__mcp_message_reply")
    calls: list[dict] = []

    async def _func(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({"success": True}))]
        )

    tool.func = _func
    await _patch_tools(monkeypatch, [tool])
    monkeypatch.setattr(
        "app.core.channel.input.mcp_message.REPLY_CHUNK_DELAY_SECONDS", 0.0
    )
    return calls


async def _send_reply(content: str) -> None:
    from app.core.events.registry import OutboundReplyEvent

    await mcp_message_channel.on_outbound_reply(
        OutboundReplyEvent(
            channel="mcp_message",
            recipient="wxid_abc",
            content=content,
            project_id=1,
            source_system="capability-matrix",
        )
    )
