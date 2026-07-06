#!/usr/bin/env python3
"""
EvoLoop 端到端链路测试脚本

验证四条核心链路是否畅通：
  1. Mobile -> Gateway -> Agent
  2. Agent -> Gateway -> Mobile
  3. Agent -> Gateway -> MC PHP (Redis 队列)
  4. MC PHP -> Gateway -> Agent

前置条件（请按顺序启动）：
  1. Redis: redis-server (默认 127.0.0.1:6379)
  2. Gateway: cd member-center/gateway && ./gateway
  3. Agent:   cd evoloop/backend && python -m app.main (或你的启动方式)
  4. PHP:     cd member-center/backend && php think queue:work redis --queue gateway:mc:message_sync --sleep 3 --tries 3
  5. PHP Push: cd member-center/backend && php think queue:work redis --queue gateway:push:notify --sleep 3 --tries 3

用法：
  python3 tests/integration/e2e_link_test.py
  python3 tests/integration/e2e_link_test.py --gateway http://127.0.0.1:9001 --redis redis://127.0.0.1:6379/0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import redis
import requests
import websockets

# ── 配置 ──────────────────────────────────────────────────────────────────────

DEFAULT_GATEWAY_HTTP = "http://127.0.0.1:9001"
DEFAULT_GATEWAY_WS = "ws://127.0.0.1:9001"
DEFAULT_REDIS = "redis://127.0.0.1:6379/0"

# 测试用的认证 token（需要替换为有效的用户 token 或游客 token）
# Gateway 的 WebSocket 认证：token 会拼接到 URL 查询参数
MOBILE_TOKEN = "test-mobile-token"
AGENT_TOKEN = "test-agent-token"

# 测试用的 member_id / device_key
TEST_MEMBER_ID = 1
TEST_DEVICE_KEY = "test-desktop-device-001"

# Redis 队列 key
QUEUE_MESSAGE_SYNC = "gateway:mc:message_sync"
QUEUE_PUSH_NOTIFY = "gateway:push:notify"

# ── 测试结果数据结构 ───────────────────────────────────────────────────────────


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float = 0.0
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class E2ETestRunner:
    def __init__(
        self,
        gateway_http: str,
        gateway_ws: str,
        redis_url: str,
        agent_token: str = AGENT_TOKEN,
        mobile_token: str = MOBILE_TOKEN,
        device_key: str = TEST_DEVICE_KEY,
        member_id: int = TEST_MEMBER_ID,
    ):
        self.gateway_http = gateway_http.rstrip("/")
        self.gateway_ws = gateway_ws.rstrip("/")
        self.redis_client = redis.from_url(redis_url, decode_responses=False)
        self.agent_token = agent_token
        self.mobile_token = mobile_token
        self.device_key = device_key
        self.member_id = member_id
        self.results: list[TestResult] = []
        self._agent_ws: websockets.WebSocketClientProtocol | None = None
        self._mobile_ws: websockets.WebSocketClientProtocol | None = None

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        print(f"  [TEST] {msg}")

    def _assert(self, condition: bool, msg: str) -> None:
        if not condition:
            raise AssertionError(msg)

    async def _connect_agent(self) -> websockets.WebSocketClientProtocol:
        """模拟 Agent 连接 Gateway WebSocket"""
        url = f"{self.gateway_ws}/ws?token={self.agent_token}"
        ws = await websockets.connect(url)
        await ws.send(
            json.dumps(
                {
                    "version": "2.0",
                    "type": "connect",
                    "message_id": f"e2e-agent-{uuid.uuid4().hex[:8]}",
                    "timestamp": int(time.time()),
                    "body": {
                        "device_type": "agent",
                        "device_key": self.device_key,
                        "device_name": "E2E Desktop Agent",
                        "os_info": "e2e-test",
                    },
                }
            )
        )
        # 等待 system.init
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(resp)
        self._log(f"Agent system.init: {data}")
        if data.get("type") != "system.init":
            raise AssertionError(f"Expected system.init, got {data.get('type')}")
        return ws

    async def _connect_mobile(self) -> websockets.WebSocketClientProtocol:
        """模拟 Mobile 连接 Gateway WebSocket"""
        url = f"{self.gateway_ws}/ws?token={self.mobile_token}"
        ws = await websockets.connect(url)
        await ws.send(
            json.dumps(
                {
                    "version": "2.0",
                    "type": "connect",
                    "message_id": f"e2e-mobile-{uuid.uuid4().hex[:8]}",
                    "timestamp": int(time.time()),
                    "body": {
                        "device_type": "mobile",
                    },
                }
            )
        )
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(resp)
        self._log(f"Mobile system.init: {data}")
        if data.get("type") != "system.init":
            raise AssertionError(f"Expected system.init, got {data.get('type')}")
        return ws

    def _redis_flush_queues(self) -> None:
        """清空测试队列"""
        self.redis_client.delete(QUEUE_MESSAGE_SYNC, QUEUE_PUSH_NOTIFY)
        self._log("Redis queues flushed")

    def _redis_pop_message_sync(self, timeout: float = 3.0) -> dict | None:
        """从 Redis 队列弹出一个 message.sync 消息"""
        raw = self.redis_client.brpop(QUEUE_MESSAGE_SYNC, timeout=timeout)
        if raw:
            return json.loads(raw[1])
        return None

    def _redis_pop_push_notify(self, timeout: float = 3.0) -> dict | None:
        """从 Redis 队列弹出一个 push 通知"""
        raw = self.redis_client.brpop(QUEUE_PUSH_NOTIFY, timeout=timeout)
        if raw:
            return json.loads(raw[1])
        return None

    # ── 链路 1: Mobile -> Gateway -> Agent ─────────────────────────────────────

    async def test_link_mobile_to_agent(self) -> TestResult:
        """
        Mobile 通过 HTTP POST /api/v1/message/send 发送规范 Envelope，
        Gateway 转发给 Agent，Agent 应收到规范 command.relay Envelope。
        """
        name = "Mobile -> Gateway -> Agent"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            # 1. 确保 Agent 已连接
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()

            # 2. Mobile HTTP 发送规范 Envelope
            thread_id = f"test-thread-{int(time.time())}"
            message_id = str(uuid.uuid4())
            envelope = {
                "version": "2.0",
                "type": "command.relay",
                "message_id": message_id,
                "timestamp": int(time.time()),
                "body": {
                    "command_id": 0,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "action": "chat",
                    "content": {"text": "Hello from E2E test"},
                },
            }
            payload = {
                "target_device_key": self.device_key,
                "envelope": envelope,
            }
            http_resp = requests.post(
                f"{self.gateway_http}/api/v1/message/send",
                json=payload,
                headers={"Authorization": f"Bearer {self.mobile_token}"},
                timeout=10,
            )
            self._assert(
                http_resp.status_code == 200,
                f"HTTP failed: {http_resp.status_code} {http_resp.text}",
            )
            resp_body = http_resp.json()
            self._assert(resp_body.get("code") == 0, f"Gateway error: {resp_body}")
            details["command_id"] = resp_body.get("data", {}).get("command_id", "")
            details["thread_id"] = thread_id
            details["message_id"] = message_id
            self._log(
                f"Mobile HTTP sent, thread_id={thread_id}, message_id={message_id}"
            )

            # 3. Agent WebSocket 应收到 command.relay
            agent_msg_raw = await asyncio.wait_for(self._agent_ws.recv(), timeout=5.0)
            agent_msg = json.loads(agent_msg_raw)
            self._log(f"Agent received: type={agent_msg.get('type')}")

            self._assert(
                agent_msg.get("type") == "command.relay",
                f"Expected command.relay, got {agent_msg.get('type')}",
            )
            cmd_body = agent_msg.get("body", {})
            self._assert(
                cmd_body.get("thread_id") == thread_id,
                f"thread_id mismatch: {cmd_body.get('thread_id')} != {thread_id}",
            )
            self._assert(
                cmd_body.get("message_id") == message_id,
                f"message_id mismatch: {cmd_body.get('message_id')} != {message_id}",
            )
            self._assert(
                cmd_body.get("action") == "chat",
                f"action mismatch: {cmd_body.get('action')} != chat",
            )

            details["agent_received_command_id"] = cmd_body.get("command_id")
            self._log("Agent received correct command.relay ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 链路 2: Agent -> Gateway -> Mobile ─────────────────────────────────────

    async def test_link_agent_to_mobile(self) -> TestResult:
        """
        Agent 发送 message.sync 到 Gateway，
        Gateway 应广播给 Mobile WebSocket。
        """
        name = "Agent -> Gateway -> Mobile (WebSocket)"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            # 1. 确保双方已连接
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()
            if not self._mobile_ws:
                self._mobile_ws = await self._connect_mobile()

            # 2. 先清空 Mobile 的消息缓冲区（消费掉心跳等）
            await asyncio.sleep(0.5)
            while True:
                try:
                    await asyncio.wait_for(self._mobile_ws.recv(), timeout=0.3)
                except asyncio.TimeoutError:
                    break

            # 3. Agent 发送 message.sync
            thread_id = f"test-thread-{int(time.time())}"
            message_id = str(uuid.uuid4())
            sync_payload = {
                "version": "2.0",
                "type": "message.sync",
                "message_id": message_id,
                "timestamp": int(time.time()),
                "body": {
                    "device_key": self.device_key,
                    "sync_mode": "incremental",
                    "thread_id": thread_id,
                    "conversation": {
                        "id": thread_id,
                        "title": "E2E Test Conversation",
                    },
                    "messages": [
                        {
                            "message_id": "msg-1",
                            "thread_id": thread_id,
                            "role": "ai",
                            "content": "This is a test message from Agent",
                            "content_type": "text",
                            "created_at": int(time.time()),
                            "sequence_number": 1,
                        }
                    ],
                },
            }
            await self._agent_ws.send(json.dumps(sync_payload))
            self._log(f"Agent sent message.sync, thread_id={thread_id}")

            # 4. Mobile 应收到 message.sync
            mobile_msg_raw = await asyncio.wait_for(self._mobile_ws.recv(), timeout=5.0)
            mobile_msg = json.loads(mobile_msg_raw)
            self._log(f"Mobile received: type={mobile_msg.get('type')}")

            self._assert(
                mobile_msg.get("type") == "message.sync",
                f"Expected message.sync, got {mobile_msg.get('type')}",
            )
            body = mobile_msg.get("body", {})
            self._assert(body.get("thread_id") == thread_id, "thread_id mismatch")
            messages = body.get("messages", [])
            self._assert(len(messages) == 1, f"Expected 1 message, got {len(messages)}")
            self._assert(
                messages[0].get("content") == "This is a test message from Agent",
                "content mismatch",
            )

            details["mobile_received_type"] = mobile_msg.get("type")
            self._log("Mobile received correct message.sync ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 链路 3: Agent -> Gateway -> MC PHP (Redis) ─────────────────────────────

    async def test_link_agent_to_mc_redis(self) -> TestResult:
        """
        Agent 发送 message.sync 到 Gateway，
        Gateway 应将原始 payload LPUSH 到 Redis `gateway:mc:message_sync`。
        """
        name = "Agent -> Gateway -> MC PHP (Redis queue)"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()

            # 清空队列，避免历史数据干扰
            self._redis_flush_queues()

            thread_id = f"test-thread-{int(time.time())}"
            message_id = str(uuid.uuid4())
            sync_payload = {
                "version": "2.0",
                "type": "message.sync",
                "message_id": message_id,
                "timestamp": int(time.time()),
                "body": {
                    "device_key": self.device_key,
                    "sync_mode": "incremental",
                    "thread_id": thread_id,
                    "conversation": {"id": thread_id, "title": "Redis Test"},
                    "messages": [
                        {
                            "message_id": "msg-redis-1",
                            "thread_id": thread_id,
                            "role": "human",
                            "content": "Redis queue test",
                            "content_type": "text",
                            "created_at": int(time.time()),
                            "sequence_number": 1,
                        }
                    ],
                },
            }
            await self._agent_ws.send(json.dumps(sync_payload))
            self._log(f"Agent sent message.sync, thread_id={thread_id}")

            # 从 Redis 弹出消息
            redis_msg = self._redis_pop_message_sync(timeout=5.0)
            self._assert(redis_msg is not None, "No message found in Redis queue")

            # Gateway 入队的是规范 Envelope；取 body 验证业务字段
            envelope_body = redis_msg.get("body", redis_msg)
            self._assert(
                envelope_body.get("thread_id") == thread_id,
                "thread_id mismatch in Redis",
            )
            self._assert(
                envelope_body.get("device_key") == TEST_DEVICE_KEY,
                "device_key mismatch in Redis",
            )
            messages = envelope_body.get("messages", [])
            self._assert(
                len(messages) == 1, f"Expected 1 message in Redis, got {len(messages)}"
            )
            self._assert(
                messages[0].get("content") == "Redis queue test",
                "content mismatch in Redis",
            )

            details["redis_message_count"] = len(messages)
            self._log("Redis queue received correct message.sync ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 链路 4: HITL urgent 推送 ───────────────────────────────────────────────

    async def test_hitl_urgent_to_mobile(self) -> TestResult:
        """
        Agent 发送 hitl.request 到 Gateway，
        Gateway 应即时广播给 Mobile。
        """
        name = "Agent -> Gateway -> Mobile (HITL urgent)"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()
            if not self._mobile_ws:
                self._mobile_ws = await self._connect_mobile()

            # 清空 Mobile 缓冲区
            await asyncio.sleep(0.5)
            while True:
                try:
                    await asyncio.wait_for(self._mobile_ws.recv(), timeout=0.3)
                except asyncio.TimeoutError:
                    break

            thread_id = f"test-hitl-{int(time.time())}"
            hitl_payload = {
                "version": "2.0",
                "type": "hitl.request",
                "message_id": str(uuid.uuid4()),
                "timestamp": int(time.time()),
                "body": {
                    "request_id": "req-001",
                    "request_type": "confirmation",
                    "prompt": "请确认是否执行此操作？",
                    "context": thread_id,
                },
            }
            await self._agent_ws.send(json.dumps(hitl_payload))
            self._log(f"Agent sent hitl.request, thread_id={thread_id}")

            mobile_msg_raw = await asyncio.wait_for(self._mobile_ws.recv(), timeout=5.0)
            mobile_msg = json.loads(mobile_msg_raw)
            self._log(f"Mobile received: type={mobile_msg.get('type')}")

            self._assert(
                mobile_msg.get("type") == "hitl.request",
                f"Expected hitl.request, got {mobile_msg.get('type')}",
            )
            body = mobile_msg.get("body", {})
            self._assert(
                body.get("request_type") == "confirmation",
                f"Expected request_type=confirmation, got {body.get('request_type')}",
            )
            self._assert(body.get("request_id") == "req-001", "request_id mismatch")

            details["hitl_prompt"] = body.get("prompt", "")
            self._log("Mobile received correct hitl.request ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 链路 5: agent.status + Push 通知队列 ─────────────────────────────────

    async def test_command_complete_push_queue(self) -> TestResult:
        """
        Agent 发送 agent.status，Mobile 不在线时 Gateway 应写入 Push 队列。
        本测试不连接 Mobile，验证 Push 队列是否有数据。
        """
        name = "Agent -> Gateway -> Push queue (Mobile offline)"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()

            # 清空 Push 队列
            self.redis_client.delete(QUEUE_PUSH_NOTIFY)
            self._log("Push queue flushed")

            thread_id = f"test-push-{int(time.time())}"
            agent_status = {
                "version": "2.0",
                "type": "agent.status",
                "message_id": str(uuid.uuid4()),
                "timestamp": int(time.time()),
                "body": {
                    "thread_id": thread_id,
                    "command_id": 999,
                    "status": "completed",
                },
            }
            await self._agent_ws.send(json.dumps(agent_status))
            self._log(f"Agent sent agent.status, thread_id={thread_id}")

            # 由于没有 Mobile 连接，Gateway 应写入 Push 队列
            push_msg = self._redis_pop_push_notify(timeout=5.0)
            self._assert(
                push_msg is not None,
                "No push event found in Redis queue (Mobile should be offline)",
            )

            self._assert(
                push_msg.get("event_type") == "agent.status",
                f"event_type mismatch: {push_msg.get('event_type')}",
            )
            self._assert(
                push_msg.get("member_id") == self.member_id,
                f"member_id mismatch: {push_msg.get('member_id')}",
            )

            details["push_title"] = push_msg.get("title", "")
            self._log("Push queue received correct agent.status event ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 链路 6: MC PHP -> Gateway -> Agent (Webhook) ───────────────────────────

    async def test_link_mc_to_agent_webhook(self) -> TestResult:
        """
        模拟 MC PHP 发送 Webhook 到 Gateway，
        Gateway 应转发给 Agent。
        """
        name = "MC PHP -> Gateway -> Agent (Webhook)"
        start = time.time()
        details: dict[str, Any] = {}

        try:
            if not self._agent_ws:
                self._agent_ws = await self._connect_agent()

            thread_id = f"test-webhook-{int(time.time())}"
            message_id = str(uuid.uuid4())
            webhook_payload = {
                "member_id": self.member_id,
                "device_key": self.device_key,
                "envelope": {
                    "version": "2.0",
                    "message_id": message_id,
                    "type": "command.relay",
                    "source": {"kind": "mobile", "device_key": self.device_key},
                    "target": {"kind": "agent", "device_key": self.device_key},
                    "body": {
                        "command_id": 888,
                        "message_id": message_id,
                        "thread_id": thread_id,
                        "action": "chat",
                        "content": {"text": "Webhook test from MC"},
                    },
                },
            }

            # 模拟 MC PHP 调用 Gateway Webhook
            # 注意：实际签名验证可能需要 secret，这里假设测试环境允许或已配置
            resp = requests.post(
                f"{self.gateway_http}/webhook/evoloop/relay",
                json=webhook_payload,
                timeout=10,
            )
            self._log(f"Webhook response: {resp.status_code} {resp.text[:200]}")

            # 即使 HTTP 返回非 200，也尝试读取 Agent 的消息（因为 WebSocket 可能已经转发）
            # 但有些 Gateway 实现会验证签名，测试可能失败
            if resp.status_code == 200:
                body = resp.json()
                details["webhook_status"] = body.get("status")
                self._assert(
                    body.get("status") == "accepted", f"Webhook rejected: {body}"
                )

            # Agent 应收到规范 command.relay Envelope
            agent_msg_raw = await asyncio.wait_for(self._agent_ws.recv(), timeout=5.0)
            agent_msg = json.loads(agent_msg_raw)
            self._log(f"Agent received: type={agent_msg.get('type')}")

            self._assert(
                agent_msg.get("type") == "command.relay",
                f"Expected command.relay, got {agent_msg.get('type')}",
            )
            cmd_body = agent_msg.get("body", {})
            self._assert(cmd_body.get("thread_id") == thread_id, "thread_id mismatch")
            self._assert(
                cmd_body.get("message_id") == message_id, "message_id mismatch"
            )

            self._log("Agent received correct webhook command.relay ✓")

            return TestResult(
                name=name,
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
                details=details,
            )

    # ── 执行所有测试 ────────────────────────────────────────────────────────────

    async def run_all(self) -> list[TestResult]:
        print("=" * 70)
        print("EvoLoop 端到端链路测试")
        print("=" * 70)
        print(f"Gateway HTTP: {self.gateway_http}")
        print(f"Gateway WS:   {self.gateway_ws}")
        print(f"Redis:        {self.redis_client.connection_pool.connection_kwargs}")
        print("-" * 70)

        # 检查前置条件
        try:
            self.redis_client.ping()
            print("✓ Redis connected")
        except Exception as e:
            print(f"✗ Redis connection failed: {e}")
            sys.exit(1)

        try:
            r = requests.get(f"{self.gateway_http}/health", timeout=5)
            print(f"✓ Gateway HTTP reachable (status={r.status_code})")
        except Exception as e:
            print(f"⚠ Gateway HTTP not reachable: {e} (tests may fail)")

        print("-" * 70)

        tests = [
            ("链路 1/6", self.test_link_mobile_to_agent),
            ("链路 2/6", self.test_link_agent_to_mobile),
            ("链路 3/6", self.test_link_agent_to_mc_redis),
            ("链路 4/6", self.test_hitl_urgent_to_mobile),
            ("链路 5/6", self.test_command_complete_push_queue),
            ("链路 6/6", self.test_link_mc_to_agent_webhook),
        ]

        for label, test_fn in tests:
            print(f"\n{label}: {test_fn.__doc__.strip().split(chr(10))[0]}")
            result = await test_fn()
            self.results.append(result)
            status = "PASS" if result.passed else "FAIL"
            icon = "✓" if result.passed else "✗"
            print(f"  {icon} {status} ({result.duration_ms:.0f}ms)")
            if not result.passed:
                print(f"    ERROR: {result.error}")
            if result.details:
                for k, v in result.details.items():
                    print(f"    {k}: {v}")

        # 关闭连接
        if self._agent_ws:
            await self._agent_ws.close()
        if self._mobile_ws:
            await self._mobile_ws.close()

        return self.results

    def print_summary(self) -> None:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print("\n" + "=" * 70)
        print(f"测试结果: {passed}/{total} 通过")
        print("=" * 70)

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            icon = "✓" if r.passed else "✗"
            print(f"  {icon} [{status}] {r.name} ({r.duration_ms:.0f}ms)")
            if r.error:
                print(f"      Error: {r.error}")

        if passed == total:
            print("\n🎉 所有链路测试通过！")
            sys.exit(0)
        else:
            print(f"\n⚠️  {total - passed} 个测试失败，请检查链路")
            sys.exit(1)


# ── 入口 ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="EvoLoop 端到端链路测试")
    parser.add_argument(
        "--gateway", default=DEFAULT_GATEWAY_HTTP, help="Gateway HTTP 地址"
    )
    parser.add_argument(
        "--gateway-ws",
        default=None,
        help="Gateway WebSocket 地址（默认从 --gateway 推导）",
    )
    parser.add_argument("--redis", default=DEFAULT_REDIS, help="Redis 连接 URL")
    parser.add_argument(
        "--agent-token", default=AGENT_TOKEN, help="Agent WebSocket 认证 token"
    )
    parser.add_argument(
        "--mobile-token", default=MOBILE_TOKEN, help="Mobile WebSocket 认证 token"
    )
    parser.add_argument(
        "--device-key", default=TEST_DEVICE_KEY, help="测试用的 device_key"
    )
    parser.add_argument(
        "--member-id", type=int, default=TEST_MEMBER_ID, help="测试用的 member_id"
    )
    args = parser.parse_args()

    ws_url = args.gateway_ws or args.gateway.replace("http://", "ws://").replace(
        "https://", "wss://"
    )

    runner = E2ETestRunner(
        args.gateway,
        ws_url,
        args.redis,
        agent_token=args.agent_token,
        mobile_token=args.mobile_token,
        device_key=args.device_key,
        member_id=args.member_id,
    )
    try:
        asyncio.run(runner.run_all())
        runner.print_summary()
    except KeyboardInterrupt:
        print("\n\n测试被中断")
        sys.exit(130)


if __name__ == "__main__":
    main()
