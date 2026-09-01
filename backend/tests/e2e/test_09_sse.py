"""阶段：SSE 流订阅端到端测试。

覆盖：
  - 多客户端同时订阅同一线程的运行事件
  - 断连后重新订阅同一线程不崩溃
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    _SSE_STOP,
    SSEEmitter,
    _read_sse_stream,
    collect_sse_until,
    gen_thread_id,
)

pytestmark = pytest.mark.e2e


async def _open_sse_client(
    base_url: str, headers: dict[str, str], _thread_id: str, timeout: float = 90.0
) -> httpx.AsyncClient:
    """打开一个专门用于 SSE 的客户端。"""
    return httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)


async def _collect_until_any_event(
    client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 60.0,
) -> list[SSEEmitter]:
    """订阅并返回收到的第一个事件（兼容 LLM 快速失败的情况）。"""
    received: list[SSEEmitter] = []

    async def _handler(ev: SSEEmitter) -> Any:
        received.append(ev)
        return _SSE_STOP

    try:
        await _read_sse_stream(
            client,
            f"/api/v1/stream/chat/{thread_id}",
            _handler,
            timeout=timeout,
        )
    except TimeoutError:
        pass
    return received


async def _collect_until_run_end(
    client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 120.0,
) -> list[SSEEmitter]:
    """订阅并等待 run_end 事件。"""
    try:
        return await collect_sse_until(
            client,
            f"/api/v1/stream/chat/{thread_id}",
            lambda ev: ev.event == "run_end",
            timeout=timeout,
            desc=f"SSE run_end for {thread_id}",
        )
    except TimeoutError:
        return []


class TestSSEMultiClient:
    """多客户端同时订阅同一线程的运行事件。"""

    @pytest.mark.timeout(180)
    async def test_multiple_clients_receive_same_run_end(
        self,
        service_url: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        """两个独立 SSE 客户端订阅同一 thread，都应收到 run_end（或至少都不崩溃）。"""
        thread_id = gen_thread_id()
        headers = dict(http_client.headers)

        client1 = await _open_sse_client(service_url, headers, thread_id)
        client2 = await _open_sse_client(service_url, headers, thread_id)
        try:
            task1 = asyncio.create_task(
                _collect_until_run_end(client1, thread_id, timeout=120.0)
            )
            task2 = asyncio.create_task(
                _collect_until_run_end(client2, thread_id, timeout=120.0)
            )
            await asyncio.sleep(0)  # 确保两个客户端先建立连接

            resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": "多客户端 SSE 测试，请用一句话回应。",
                    "project_id": 0,
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "queued"

            events1 = await task1
            events2 = await task2
        finally:
            await client1.aclose()
            await client2.aclose()

        # 在 LLM 余额不足时可能失败，但 run_end 事件必须被两个客户端都收到
        assert any(e.event == "run_end" for e in events1), (
            f"客户端 1 未收到 run_end: {[e.event for e in events1]}"
        )
        assert any(e.event == "run_end" for e in events2), (
            f"客户端 2 未收到 run_end: {[e.event for e in events2]}"
        )


class TestSSEReconnect:
    """SSE 断连后重新订阅。"""

    @pytest.mark.timeout(180)
    async def test_reconnect_after_first_event_does_not_crash(
        self,
        service_url: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        """第一个客户端收到任意事件后断开，第二个客户端重新订阅应能建立连接。"""
        thread_id = gen_thread_id()
        headers = dict(http_client.headers)

        client1 = await _open_sse_client(service_url, headers, thread_id)
        try:
            first_task = asyncio.create_task(
                _collect_until_any_event(client1, thread_id, timeout=60.0)
            )
            await asyncio.sleep(0)

            resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": "SSE 断连重连测试。",
                    "project_id": 0,
                },
            )
            assert resp.status_code == 200, resp.text

            first_events = await first_task
        finally:
            await client1.aclose()

        # 第二个客户端重新订阅；允许没有新事件（运行已结束或事件不可回放）
        client2 = await _open_sse_client(service_url, headers, thread_id)
        try:
            reconnect_events = await _collect_until_any_event(
                client2, thread_id, timeout=5.0
            )
        except TimeoutError:
            reconnect_events = []
        finally:
            await client2.aclose()

        # 关键断言：重新订阅不报错，HTTP 流状态正常；client1 必须至少收到一个事件
        assert first_events, (
            f"首次订阅未收到任何事件，无法验证重连场景: thread={thread_id}"
        )
        # 如果重连接收到了事件，事件类型必须是正常的 SSE 事件之一
        if reconnect_events:
            assert all(
                e.event
                in {
                    "run_start",
                    "run_end",
                    "message",
                    "token",
                    "progress",
                    "activity",
                }
                for e in reconnect_events
            ), (
                f"重连接收到异常事件: {[e.event for e in reconnect_events]}"
            )

