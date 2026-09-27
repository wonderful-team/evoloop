"""Integration tests for SSE disconnect/reconnect (Last-Event-ID resume).

场景（对应 stream.py 的断连重连设计）：
1. 客户端断开期间，服务端继续向 thread 发布事件（写入 EventReplayBuffer）。
2. 客户端重连时带 Last-Event-ID: <seq>（EventSource 自动回传上一条事件 id）。
3. 服务端应回放区间 (last_seq, baseline_seq] 的事件，与实时流零重叠、
   不重不漏，之后实时事件继续下发（且标注 id: 供后续续传）。

使用真实 LocalMessageBroker + InMemoryPubSubAdapter（EMBEDDED_MODE=true），
通过 httpx ASGITransport 真实走 stream_chat 路由，仅对
activity_monitor.get_activity 打桩（避免依赖 activity 快照）。

注意：httpx.ASGITransport 会把整个 ASGI response 缓冲到 app 结束才交给
aiter_raw()/aread()。因此测试中把 pubsub.get_message patch 成有限流——
空等超时或收到指定数量消息后抛 StopAsyncIteration，让 generator 正常收尾，
从而能读到完整响应体。实时事件的测试靠后台任务在流存活期间 publish 完成。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.engine.message.broker import (
    event_replay_buffer,
    get_message_broker,
)


@pytest.fixture
def sse_broker():
    """真实 broker + 干净的回放缓冲状态（按 thread 隔离）。"""
    broker = get_message_broker()
    # buffer 是进程级单例，清理该 thread 残留状态避免跨用例污染
    for tid in (
        "thread-reconnect",
        "thread-full-replay",
        "thread-live-seq",
    ):
        event_replay_buffer._buffers.pop(tid, None)
        event_replay_buffer._seqs.pop(tid, None)
    yield broker


async def _no_activity(_thread_id):
    return None


def _patch_activity(monkeypatch):
    from app.api.routes import stream as stream_mod

    monkeypatch.setattr(
        stream_mod,
        "activity_monitor",
        SimpleNamespace(get_activity=_no_activity),
    )


def _patch_pubsub_finite(
    monkeypatch,
    exit_after_messages: int | None = None,
    no_message_timeout: float = 0.2,
):
    """让 InMemoryPubSubAdapter.get_message 在空等或收够消息后结束 SSE 流。

    httpx.ASGITransport 会缓冲整个响应直到 ASGI app 结束；stream_chat
    是无限流，必须让 generator 正常收尾才能读到 body。通过抛出
    StopAsyncIteration 让 StreamingResponse 关闭，与 test_stream.py 中
    FakePubSub 的退出语义一致。
    """
    from app.infrastructure.cache.file.pubsub import InMemoryPubSubAdapter

    original = InMemoryPubSubAdapter.get_message
    state = {"seen": 0}

    async def _finite_get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0  # noqa: ARG001
    ):
        # 先用较短超时等一条真实消息；没等到就结束流。
        msg = await original(
            self,
            ignore_subscribe_messages=ignore_subscribe_messages,
            timeout=no_message_timeout,
        )
        if msg:
            state["seen"] += 1
            return msg
        if (
            exit_after_messages is not None
            and state["seen"] >= exit_after_messages
        ):
            raise StopAsyncIteration
        raise StopAsyncIteration

    monkeypatch.setattr(
        InMemoryPubSubAdapter, "get_message", _finite_get_message
    )


def _parse_sse(body: str):
    """把 SSE 文本解析为 [{event, id, data}] 列表。"""
    events = []
    current = {}
    for line in body.splitlines():
        if not line.strip():
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        value = value.lstrip()
        current[key] = value
    if current:
        events.append(current)
    return events


async def _drain_until(resp, needle, max_chunks=100):
    """从 SSE 流读取 chunk，直到累计文本包含 needle（读到即返回）。

    无限流不会自然结束，读到目标就停；退出 with 块时 httpx 会
    关闭底层流并取消 server generator，不会挂起。
    """
    chunks = []
    it = resp.aiter_raw()  # 复用同一个迭代器，httpx 流只能消费一次
    for _ in range(max_chunks):
        chunk = await it.__anext__()
        text = chunk.decode("utf-8", errors="replace")
        chunks.append(text)
        if needle in "".join(chunks):
            break
    return "".join(chunks)


async def test_reconnect_resumes_with_last_event_id(
    client, monkeypatch, sse_broker
):
    """断连期间发布的事件，重连带 Last-Event-ID 后应恰好回放缺失区间，不重不漏。"""
    _patch_activity(monkeypatch)
    _patch_pubsub_finite(monkeypatch)
    thread = "thread-reconnect"

    # --- 首次连接：读到 seq=1 后断开 ---
    await sse_broker.publish(
        f"chat:{thread}:events", {"type": "token", "text": "first"}
    )

    async with client.stream("GET", f"/stream/chat/{thread}") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        first_body = await _drain_until(resp, "first")
    assert "id: 1" in first_body
    assert "first" in first_body

    # --- 断开期间：继续发布 seq=2, 3 ---
    await sse_broker.publish(
        f"chat:{thread}:events", {"type": "token", "text": "second"}
    )
    await sse_broker.publish(
        f"chat:{thread}:events", {"type": "status", "status": "running"}
    )

    # --- 重连：带 Last-Event-ID=1，应回放 seq=2,3，不再重复 seq=1 ---
    headers = {"Last-Event-ID": "1"}
    async with client.stream(
        "GET", f"/stream/chat/{thread}", headers=headers
    ) as resp:
        assert resp.status_code == 200
        body = await _drain_until(resp, "running")

    events = _parse_sse(body)

    ids = [e.get("id") for e in events if e.get("id")]
    texts = [e.get("data", "") for e in events]

    assert "2" in ids and "3" in ids, f"应回放 seq=2,3，实际 {ids}"
    assert "1" not in ids, "seq=1 不应重复回放（Last-Event-ID 已消费）"
    assert any("second" in t for t in texts)
    assert any("running" in t for t in texts)


async def test_reconnect_full_replay_without_last_event_id(
    client, monkeypatch, sse_broker
):
    """无 Last-Event-ID（首次连接/清缓存）应回放整个缓冲窗口。"""
    _patch_activity(monkeypatch)
    _patch_pubsub_finite(monkeypatch)
    thread = "thread-full-replay"

    for i in range(3):
        await sse_broker.publish(
            f"chat:{thread}:events", {"type": "token", "text": f"msg-{i}"}
        )

    async with client.stream("GET", f"/stream/chat/{thread}") as resp:
        assert resp.status_code == 200
        body = await _drain_until(resp, "msg-2")

    events = _parse_sse(body)
    ids = [e.get("id") for e in events if e.get("id")]
    texts = "".join(e.get("data", "") for e in events)

    assert ids == ["1", "2", "3"], f"应全量回放 1..3，实际 {ids}"
    assert all(f"msg-{i}" in texts for i in range(3))


async def test_reconnect_real_time_events_carry_seq_id(
    client, monkeypatch, sse_broker
):
    """实时（非回放）事件也标注 id: seq，确保下一次断点续传可继续。"""
    _patch_activity(monkeypatch)
    # 收到一条实时消息后结束流；后台任务负责在流存活期间 publish live。
    _patch_pubsub_finite(
        monkeypatch, exit_after_messages=1, no_message_timeout=2.0
    )
    thread = "thread-live-seq"

    # 先发布一条并连接（回放 seq=1）
    await sse_broker.publish(
        f"chat:{thread}:events", {"type": "token", "text": "pre"}
    )

    async def _publish_live():
        await asyncio.sleep(0.3)
        await sse_broker.publish(
            f"chat:{thread}:events", {"type": "token", "text": "live"}
        )

    asyncio.create_task(_publish_live())

    async with client.stream("GET", f"/stream/chat/{thread}") as resp:
        assert resp.status_code == 200
        body = await _drain_until(resp, "live")

    assert "id: 1" in body
    assert "id: 2" in body
    assert "pre" in body
    assert "live" in body
