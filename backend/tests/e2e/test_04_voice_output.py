"""阶段4：语音输出 / TTS 播报规则端到端测试（对应文档「附A 阶段4」、「十八」）。

覆盖数据契约（voice.route_result 信封）：
  - done：L0 宏命中并成功执行 → {status:"done", summary:话术}
  - cancelled：cancel 动作且确有任务被取消 → {status:"cancelled"}
  - 幂等：相同 message_id 重复 voice.route → duplicate_no_cache / 缓存终态
  - failed/cancelled 信封不触发 TTS（无 Volc 客户端时 push_tts_* 直接跳过，
    由第 4 步信封契约验证，不校验音频字节）
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.e2e.test_02_routing import _create_routable_macro, _wait_for_macro_in_spec

from .conftest import VoiceConn, gen_message_id

pytestmark = pytest.mark.e2e


async def _safe_macro(http_client: httpx.AsyncClient) -> str:
    """创建一个无副作用的 wait 宏（1ms）并等待其进入 L0 规格，返回 macro_id。

    ``_create_routable_macro`` 使用真实 trigger "麻烦对对对"；同名/同 trigger
    冲突时最新确认的宏优先，该 trigger 由调用方作为路由文本发送。
    """
    macro_id = await _create_routable_macro(http_client, "ack", "麻烦对对对")
    await _wait_for_macro_in_spec(http_client, macro_id)
    return macro_id


class TestVoiceResultEnvelope:
    """十八 TTS 成功/失败/取消信封契约。"""

    @pytest.mark.timeout(60)
    async def test_voice_done_envelope(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """L0 宏命中成功 → 终态 done 信封 + 播报话术（"完成"）。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            body = env["body"]
            assert body["status"] == "done"
            assert body["summary"] == "完成"
            assert body["thread_id"] == voice_conn.thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(60)
    async def test_voice_macro_empty_is_done(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """无活跃任务时命中 wait 宏 → 终态 done 信封（非 cancelled）。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            body = env["body"]
            assert body["status"] == "done"
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(60)
    async def test_voice_route_duplicate_idempotency(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """相同 message_id 重复路由 → 幂等处理（缓存终态或 duplicate_no_cache）。"""
        macro_id = await _safe_macro(http_client)
        try:
            mid = gen_message_id()
            await voice_conn.send_route("麻烦对对对", message_id=mid)
            first = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert first["body"]["status"] == "done"

            # 重复请求：命中幂等缓存，不重复执行
            await voice_conn.send_route("麻烦对对对", message_id=mid)
            second = await voice_conn.wait_route_result(timeout=20.0)
            status = second["body"]["status"]
            assert status in ("done", "duplicate_no_cache"), second["body"]
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(60)
    async def test_voice_route_result_is_canonical_envelope(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """voice.route_result 终态信封为 canonical（version 2.0 + message_id）。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert env["version"] == "2.0"
            assert isinstance(env["message_id"], str)
            assert env["type"] == "voice.route_result"
            assert env["body"]["summary"] == "完成"
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestVoiceNoTTSOnFailure:
    """十八 失败/取消状态不触发 TTS（无 Volc 客户端时安全跳过，不报错）。"""

    @pytest.mark.timeout(120)
    async def test_voice_cancelled_envelope_no_tts(self, voice_conn: VoiceConn) -> None:
        """复合意图委托 Agent 后 voice.cancel 硬掐断 → cancelled/failed 终态信封，不 TTS。"""
        await voice_conn.send_route("先搜索前端代码再部署到测试环境")
        # 等待 worker 注册完成，然后循环发送 cancel 确保命中
        await asyncio.sleep(1.0)
        for _ in range(5):
            await voice_conn.send_type(
                "voice.cancel", {"thread_id": voice_conn.thread_id}
            )
            await asyncio.sleep(0.5)

        env = await voice_conn.wait_terminal_route_result(timeout=60.0)
        status = env["body"]["status"]
        assert status in (
            "cancelled",
            "failed",
        ), f"硬掐断后期望 cancelled/failed，实际: {status}"
        # 非 done 状态不触发 TTS，push_voice_result 仅在 status==done 时合成音频
        assert env["body"]["thread_id"] == voice_conn.thread_id


class TestVoiceRouteEdgeCases:
    """十八 语音路由边缘输入。"""

    @pytest.mark.timeout(60)
    async def test_voice_route_empty_text(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """空文本 route 不应导致 WS 崩溃，应返回可识别 route_result 或明确错误。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("")
            # 空文本可能快速失败，也可能被 L0 处理；关键是不崩溃并返回某种反馈
            env = await voice_conn._drain_until(
                lambda e: e.get("type") in ("voice.route_result", "system.error"),
                timeout=20.0,
            )
            if env is not None:
                assert env.get("type") in ("voice.route_result", "system.error")
                if env.get("type") == "voice.route_result":
                    assert env["body"]["status"] in ("done", "failed", "cancelled")
            # 无论是否收到反馈，连接必须保持可用
            await voice_conn.send_route("麻烦对对对")
            final_env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert final_env["type"] == "voice.route_result"
            assert final_env["body"]["status"] == "done"
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestVoiceL0MacroRouting:
    """十八 语音 L0 宏路由（协议层，不执行桌面）。"""

    @pytest.mark.timeout(60)
    async def test_voice_macro_routes_without_execution(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """"麻烦对对对"命中 wait 宏，返回 done 信封 + 动作信息。

        注意：这是后端协议 E2E，验证路由决策与 voice.route_result 信封；
        wait 宏仅 sleep 1ms，不产生桌面副作用。
        """
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            body = env["body"]
            assert body["status"] == "done"
            assert body["summary"] == "完成"
            assert body["thread_id"] == voice_conn.thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestVoiceMultiTurnFollowUp:
    """十八 同线程语音多轮追问：L0 终态后新请求应正常处理。"""

    @pytest.mark.timeout(90)
    async def test_voice_multi_turn_macro_then_macro(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """先触发 wait 宏，再触发同一宏：两次 route 在同一 thread 独立处理。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            first = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert first["body"]["status"] == "done"
            assert first["body"]["summary"] == "完成"

            await voice_conn.send_route("麻烦对对对")
            second = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert second["body"]["status"] == "done"
            assert second["body"]["summary"] == "完成"
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")
