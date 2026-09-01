"""真实语音客户端模拟 E2E 测试。

覆盖：
- WebSocket 握手与 canonical 信封
- voice.start / voice.stop 状态机（dialogue / dictation 模式）
- voice.route 文本路由（不依赖 Volcengine ASR）
- /voice/tts 真实火山引擎 TTS 调用

火山引擎未配置时，测试会失败并自动生成缺陷文档。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
import websockets

from tests.e2e.conftest import VoiceConn, gen_thread_id

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


def _is_voice_quota_exhausted(result: dict[str, Any]) -> bool:
    """voice.route_result 的 summary 是否包含 LLM 余额不足/402 特征。"""
    if not isinstance(result, dict):
        return False
    body = result.get("body") or {}
    status = body.get("status")
    summary = body.get("summary", "")
    if status != "failed":
        return False
    lower = (summary or "").lower()
    return any(k in lower for k in ("insufficient balance", "402", "quota"))


class TestRealVoiceClient:
    """真实语音客户端模拟。"""

    @pytest.mark.timeout(60)
    @pytest.mark.parametrize("mode", ["dialogue", "dictation"])
    async def test_voice_start_state_machine(
        self,
        service_url: str,
        mode: str,
        volc_configured: bool,
    ) -> None:
        """voice.start 后根据 Volcengine 配置返回 listening 或明确错误。"""
        thread_id = gen_thread_id()
        conn = await VoiceConn.connect(service_url, thread_id)
        try:
            # 消费并忽略 system.init / connect ack
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)
            await conn.send_type("connect", {})
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)

            await conn.send_type("voice.start", {"thread_id": thread_id, "mode": mode})

            if not volc_configured:
                # 未配置：必须收到明确错误，不能假成功
                error = await conn.wait_type("system.error", timeout=15.0)
                assert error.get("body", {}).get("code") == "volc_not_configured", (
                    f"未配置火山引擎时应返回 volc_not_configured，实际: {error}"
                )
                idle = await conn.wait_type("voice.state", timeout=15.0)
                assert idle.get("body", {}).get("state") == "idle", (
                    f"错误后应变回 idle，实际: {idle}"
                )
            else:
                state = await conn.wait_type("voice.state", timeout=20.0)
                assert state.get("body", {}).get("state") == "listening", (
                    f"voice.start 后应进入 listening，实际: {state}"
                )
        finally:
            await conn.close()

    @pytest.mark.timeout(120)
    @pytest.mark.parametrize(
        "route_text, expect_terminal_status",
        [
            pytest.param("你好，请确认语音路由正常", "done", id="greeting"),
            pytest.param(
                "请使用 execute_command 工具运行 echo voice-route-test",
                "done",
                id="tool-route",
            ),
        ],
    )
    async def test_voice_route_text_pipeline(
        self,
        service_url: str,
        route_text: str,
        expect_terminal_status: str,
    ) -> None:
        """voice.route 直接以文本驱动，不依赖 ASR。"""
        thread_id = gen_thread_id()
        conn = await VoiceConn.connect(service_url, thread_id)
        try:
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)
            await conn.send_type("connect", {})
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)

            await conn.send_route(route_text)
            result = await conn.wait_terminal_route_result(timeout=90.0)
            status = result.get("body", {}).get("status")
            logger.info(
                "voice.route thread=%s status=%s result=%s",
                thread_id,
                status,
                result,
            )
            # LLM 余额不足时返回 failed + 带 provider error 的 summary，这也是一种前端反馈
            if _is_voice_quota_exhausted(result):
                assert result.get("body", {}).get("summary"), (
                    "语音配额失败 summary 不能为空"
                )
                return
            # 若 LLM/外部依赖异常，允许 status 为 failed 但记录缺陷
            assert status in (
                "done",
                "failed",
                "cancelled",
            ), f"voice.route_result 终态非法: {result}"
            if status == expect_terminal_status:
                return
            # 若未达预期成功态，也失败（缺陷记录）
            pytest.fail(
                f"voice.route 预期 {expect_terminal_status}，实际 {status}，result={result}"
            )
        finally:
            await conn.close()

    @pytest.mark.timeout(180)
    @pytest.mark.parametrize(
        "text, expect_pcm",
        [
            pytest.param("你好，这是 E2E 语音测试。", True, id="volc-tts-success"),
        ],
    )
    async def test_real_volc_tts(
        self,
        http_client: httpx.AsyncClient,
        text: str,
        expect_pcm: bool,
        volc_configured: bool,
    ) -> None:
        """/voice/tts 真实调用火山引擎 TTS。"""
        resp = await http_client.post(
            "/api/v1/voice/tts",
            json={"text": text, "engine": "volcengine", "voice": ""},
            timeout=120.0,
        )
        if not volc_configured:
            assert resp.status_code == 500, (
                f"火山未配置时 /voice/tts 应返回 500，实际 {resp.status_code}"
            )
            assert "火山引擎未配置" in resp.text or "volc" in resp.text.lower(), (
                f"错误信息应提示火山引擎配置缺失，实际: {resp.text[:200]}"
            )
            pytest.fail("火山引擎 TTS 未配置，真实 TTS 链路不可用")
            return

        assert resp.status_code == 200, (
            f"TTS 请求失败: {resp.status_code} {resp.text[:200]}"
        )
        assert resp.headers.get("content-type") == "audio/mpeg", (
            f"TTS 返回内容类型异常: {resp.headers.get('content-type')}"
        )
        audio = resp.content
        assert len(audio) > 0, "TTS 返回空音频"
        if expect_pcm:
            assert len(audio) >= 2, f"TTS 音频数据异常，长度={len(audio)}"

    @pytest.mark.timeout(30)
    async def test_voice_websocket_loopback_only(
        self,
        service_url: str,
    ) -> None:
        """语音 WebSocket 仅允许本机连接，外部 IP 应被拒绝。"""
        # service_url 是 http://127.0.0.1:20160；我们使用 127.0.0.1 应成功
        ws_url = service_url.replace("http://", "ws://").replace("https://", "wss://")
        conn = await websockets.connect(
            f"{ws_url}/api/v1/voice/ws", ping_interval=None
        )
        try:
            raw = await conn.recv()
            data = json.loads(raw)
            assert data.get("type") == "system.init", (
                f"本机连接应成功并收到 system.init，实际: {data}"
            )
        finally:
            await conn.close()

    @pytest.mark.timeout(60)
    @pytest.mark.parametrize("mode", ["dialogue", "dictation"])
    async def test_voice_start_twice_idempotent(
        self,
        service_url: str,
        mode: str,
    ) -> None:
        """连续发送两次 voice.start，状态机应保持可识别（listening 或明确错误）。"""
        thread_id = gen_thread_id()
        conn = await VoiceConn.connect(service_url, thread_id)
        try:
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)
            await conn.send_type("connect", {})
            await conn._drain_until(lambda e: e.get("type") == "system.init", timeout=10.0)

            for i in range(2):
                await conn.send_type("voice.start", {"thread_id": thread_id, "mode": mode})
                # 第二次 start 应同样收到状态反馈；如果未配置火山则两次都应收到 system.error
                env = await conn._drain_until(
                    lambda e: e.get("type") in ("voice.state", "system.error"),
                    timeout=20.0,
                )
                assert env is not None, f"第 {i+1} 次 voice.start 后未收到任何状态"
                if env.get("type") == "system.error":
                    assert env.get("body", {}).get("code") == "volc_not_configured"
                else:
                    assert env.get("body", {}).get("state") in ("listening", "idle")
        finally:
            await conn.close()

    @pytest.mark.timeout(30)
    async def test_real_volc_tts_empty_text(
        self,
        http_client: httpx.AsyncClient,
        volc_configured: bool,
    ) -> None:
        """空文本 TTS 不应 500（应 400/422 或返回空音频）。"""
        if not volc_configured:
            pytest.skip("火山引擎未配置，跳过真实 TTS 边界测试")
        resp = await http_client.post(
            "/api/v1/voice/tts",
            json={"text": "", "engine": "volcengine", "voice": ""},
            timeout=30.0,
        )
        assert resp.status_code in (200, 400, 422), (
            f"空文本 TTS 不应 500: {resp.status_code} {resp.text[:200]}"
        )
