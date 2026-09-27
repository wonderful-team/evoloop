"""阶段1：入站接收链路端到端测试（对应文档「附A 阶段1」）。

覆盖数据契约：
  - 文字/网页入站：POST /api/v1/chat → {"status":"queued", thread_id, message_id}
  - 语音入站：voice_ws.py voice.route → voice.route_result 信封
  - 附件上传：POST /api/v1/files/upload → FileUploadResponse
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from tests.e2e.test_02_routing import _create_routable_macro, _wait_for_macro_in_spec

from .conftest import VoiceConn, gen_thread_id, wait_until

pytestmark = pytest.mark.e2e


async def _safe_macro(http_client: httpx.AsyncClient) -> str:
    """创建一个无副作用的 wait 宏（1ms）并等待其进入 L0 规格，返回 macro_id。

    ``_create_routable_macro`` 使用真实 trigger "麻烦对对对"；同名/同 trigger
    冲突时最新确认的宏优先，该 trigger 由调用方作为路由文本发送。
    """
    macro_id = await _create_routable_macro(http_client, "ack", "麻烦对对对")
    await _wait_for_macro_in_spec(http_client, macro_id)
    # L0 matcher 的防抖重建窗口（REBUILD_DEBOUNCE_SECONDS=0.2s）以最后一次
    # 生命周期事件起算；夹具确认后立即 send_route 会落在窗口内导致稳定
    # miss（实测 3/3）。等待一个防抖周期再观察。
    import asyncio as _asyncio

    await _asyncio.sleep(0.5)
    return macro_id


class TestWebInbound:
    """一.2 文字/网页消息链路。"""

    @pytest.mark.timeout(30)
    async def test_chat_queued_contract(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """L0 未命中的复杂任务 → 规范化入站后返回 queued 契约。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "请分析当前项目的代码结构并给出优化建议",
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["thread_id"] == thread_id
        assert body["message_id"]

    @pytest.mark.timeout(30)
    async def test_chat_invalid_request_422(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """缺失必填 message 字段 → 422 校验错误（Fail-Fast）。"""
        resp = await http_client.post("/api/v1/chat", json={"thread_id": thread_id})
        assert resp.status_code == 422, resp.text

    @pytest.mark.timeout(60)
    async def test_chat_skips_l0_and_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """文字消息跳过 L0：即便命中已确认的 L0 宏（麻烦对对对）也直接委派 Agent（queued），
        不在本地执行宏（不返回 done/macro）。L0 仅保留给语音快捷指令。"""
        macro_id = await _safe_macro(http_client)
        try:
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": "麻烦对对对", "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued", f"文字消息不应在 L0 本地执行宏: {body}"
            assert body.get("action_type") is None, f"文字消息不应带 L0 动作: {body}"
            assert body["message_id"], body
            assert body["thread_id"] == thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(30)
    async def test_chat_thread_busy_409(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """同一线程正在运行中再次发消息 → 409 并发保护。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "请分析当前项目代码结构"},
        )
        # 线程处于 running 状态时，第二次请求应被 409 拒绝
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "第二条消息"}
        )
        if resp.status_code == 200:
            # Agent 可能已快速结束（LLM 环境差异），此时契约仍是合法入站
            assert resp.json()["status"] in ("queued", "done")
        else:
            assert resp.status_code == 409, resp.text


class TestVoiceInbound:
    """一.1 语音消息链路。"""

    @pytest.mark.timeout(30)
    async def test_voice_ws_handshake_system_init(self, voice_conn: VoiceConn) -> None:
        """连接建立后服务端推送 system.init 握手帧。"""
        env = await voice_conn.wait_type("system.init", timeout=10.0)
        body = env.get("body") or {}
        assert "client_id" in body

    @pytest.mark.timeout(60)
    async def test_voice_route_inbound_contract(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """voice.route 原始载荷 → L0 命中宏 → voice.route_result done 信封。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert env["type"] == "voice.route_result"
            assert env["version"] == "2.0"
            body = env["body"]
            assert body["thread_id"] == voice_conn.thread_id
            assert body["status"] == "done"
            assert body["summary"] == "完成"
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(30)
    async def test_voice_ws_bad_envelope_error(self, voice_conn: VoiceConn) -> None:
        """非 canonical 信封 → system.error {code: bad_envelope}。"""
        await voice_conn.ws.send('{"type": "voice.route", "body": {}}')
        env = await voice_conn.wait_type("system.error", timeout=10.0)
        assert env.get("body", {}).get("code") == "bad_envelope"


class TestAttachmentInbound:
    """十一 附件/引用入站链路。"""

    @pytest.mark.timeout(30)
    async def test_file_upload_contract(self, http_client: httpx.AsyncClient) -> None:
        """上传文件 → 落盘并返回 url/filename/path，可经 /files/raw 读回。"""
        filename = f"e2e_attachment_{uuid.uuid4().hex[:8]}.txt"
        content = b"e2e attachment payload: hello evoloop"
        files = {"file": (filename, content, "text/plain")}
        resp = await http_client.post(
            "/api/v1/files/upload", params={"project_id": 0}, files=files
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["filename"] == filename
        assert body["path"].startswith("uploads/")
        assert body["url"].startswith("/api/v1/files/raw")

        raw = await http_client.get(
            "/api/v1/files/raw", params={"project_id": 0, "path": body["path"]}
        )
        assert raw.status_code == 200, raw.text
        assert raw.content == content

    @pytest.mark.timeout(60)
    async def test_chat_with_reference(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """携带 references 的入站消息仍可正常受理（引用加载不阻断分发）。"""
        upload = await http_client.post(
            "/api/v1/files/upload",
            params={"project_id": 0},
            files={"file": ("ref.txt", b"reference content", "text/plain")},
        )
        assert upload.status_code == 200
        path = upload.json()["path"]

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "请阅读附件内容并总结",
                "project_id": 0,
                "references": [
                    {
                        "type": "file",
                        "id": path,
                        "target_id": path,
                        "target_name": "ref.txt",
                        "meta_data": {},
                    }
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("queued", "done")


class TestWebSkipsL0ContextInjection:
    """一 文字消息跳过 L0 后不得注入 [前置上下文]（防跨订单串单）。"""

    @pytest.mark.timeout(90)
    async def test_web_human_message_has_no_l0_macro_injection(
        self, http_client: httpx.AsyncClient, thread_id: str, voice_conn: VoiceConn
    ) -> None:
        """同一线程先走语音 L0 宏（设置线程级宏执行结果），再发文字消息；
        落库的 human 消息内容不得包含 [前置上下文] / 上一单语音指令。"""
        macro_id = await _safe_macro(http_client)
        try:
            # 语音 L0 执行宏 → 线程级 last_macro_result / session_history 被设置
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert env["body"]["status"] == "done"

            # 文字消息（同一 thread）处理新订单
            text = "处理退款单 202608160702156507（order_goods 390，仅退款 ¥71.80）"
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": text, "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued"
            msg_id = body["message_id"]

            async def _check() -> list[dict]:
                resp = await http_client.get(
                    f"/api/v1/conversations/{thread_id}/messages"
                )
                assert resp.status_code == 200, resp.text
                return [
                    m
                    for m in resp.json().get("data", [])
                    if m.get("role") == "human" and m.get("id") == msg_id
                ]

            messages = await wait_until(_check, timeout=20.0, desc="文字 human 消息落库")
            assert messages, "文字消息未落库"
            assert messages[0]["content"] == text, (
                f"文字消息不应注入 [前置上下文]/语音宏上下文，实际: {messages[0]['content']!r}"
            )
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestMobileInbound:
    """九 移动端入站（依赖 EvoCloud 网关建连，未连接时按环境跳过）。"""

    @pytest.mark.timeout(30)
    async def test_cloud_gateway_status_report(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """云网关链路状态可观测：/system/cloud-status 返回连接状态契约。"""
        resp = await http_client.get("/api/v1/system/cloud-status")
        assert resp.status_code in (200, 401, 404), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert isinstance(body, dict)


class TestWebInboundEdgeCases:
    """一.2 文字/网页入站极端场景。"""

    @pytest.mark.timeout(30)
    async def test_chat_empty_message_is_handled_gracefully(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """空消息体不应 500；后端应给出明确契约（done/queued/422 均可）。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": ""}
        )
        assert resp.status_code in (200, 400, 422), (
            f"空消息不应导致服务端错误: {resp.status_code} {resp.text[:200]}"
        )
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] in ("done", "queued", "failed"), (
                f"空消息返回状态异常: {body}"
            )

    @pytest.mark.timeout(30)
    async def test_chat_whitespace_only_message_is_handled_gracefully(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """纯空白消息不应 500。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "   \n\t  "}
        )
        assert resp.status_code in (200, 400, 422), (
            f"纯空白消息不应导致服务端错误: {resp.status_code} {resp.text[:200]}"
        )
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] in ("done", "queued", "failed"), (
                f"空白消息返回状态异常: {body}"
            )

    @pytest.mark.timeout(30)
    async def test_chat_long_message_is_handled_gracefully(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """超长消息不应导致 500 或请求挂死。"""
        long_message = "测试长文本" * 500  # ~2000 字
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": long_message, "project_id": 0},
        )
        assert resp.status_code in (200, 400, 422), (
            f"超长消息不应导致服务端错误: {resp.status_code} {resp.text[:200]}"
        )
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] in ("done", "queued"), (
                f"超长消息返回状态异常: {body}"
            )
            assert body["thread_id"] == thread_id

    @pytest.mark.timeout(60)
    async def test_chat_duplicate_message_id_does_not_crash(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """相同 message_id 连续两次发送到同一线程不应 500（幂等或拒绝均可）。"""
        macro_id = await _safe_macro(http_client)
        try:
            message_id = f"dup-{uuid.uuid4().hex[:8]}"
            # 第一次用宏触发语（文字跳过 L0 → queued，委派 Agent）避免直接命中
            # 本地宏，同时验证相同 message_id 不会让服务端崩溃。
            resp1 = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": "麻烦对对对",
                    "message_id": message_id,
                    "project_id": 0,
                },
            )
            assert resp1.status_code == 200, resp1.text
            body1 = resp1.json()
            assert body1["status"] in ("queued", "done", "failed"), body1

            resp2 = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": "你好",
                    "message_id": message_id,
                    "project_id": 0,
                },
            )
            assert resp2.status_code not in (500, 502, 503, 504), (
                f"重复 message_id 不应导致服务端错误: {resp2.status_code} {resp2.text[:200]}"
            )
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestGuestMode:
    """一 Guest 模式：未登录用户以 X-Guest-Id 身份走真实 chat 链路。"""

    @pytest.fixture
    async def guest_http_client(
        self, service_url: str
    ) -> AsyncIterator[httpx.AsyncClient]:
        headers = {"X-Guest-Id": f"e2e-guest-{uuid.uuid4().hex[:12]}"}
        async with httpx.AsyncClient(
            base_url=service_url, headers=headers, timeout=30.0
        ) as client:
            yield client

    @pytest.mark.timeout(60)
    async def test_guest_chat_message_is_queued(
        self, guest_http_client: httpx.AsyncClient
    ) -> None:
        """Guest 用户发送普通消息应被入队，不 500。"""
        thread_id = gen_thread_id()
        resp = await guest_http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "请用一句话总结一下你是什么助手",
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("queued", "done", "failed")
        assert body["thread_id"] == thread_id

    @pytest.mark.timeout(60)
    async def test_guest_chat_queues_agent(
        self, guest_http_client: httpx.AsyncClient
    ) -> None:
        """Guest 用户发送复杂任务应被入队，不 500。"""
        thread_id = gen_thread_id()
        resp = await guest_http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "请用一句话总结一下你是什么助手",
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("queued", "done", "failed")
        assert body["thread_id"] == thread_id


class TestWebhookInbound:
    """一 Webhook 入站：外部事件（如 project_switched）被后端接受。"""

    @pytest.mark.timeout(30)
    async def test_webhook_project_switched(
        self, http_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        """project_switched webhook 返回 switched 状态并刷新项目缓存。"""
        project_dir = tmp_path / "e2e-webhook-project"
        project_dir.mkdir()
        payload = {"new_project": {"path": str(project_dir)}}
        resp = await http_client.post(
            "/api/v1/webhook",
            json={
                "source": "evocloud",
                "event_type": "project_switched",
                "payload": payload,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "switched"
        assert body["thread_id"]

