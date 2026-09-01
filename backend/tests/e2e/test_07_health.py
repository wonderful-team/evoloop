"""阶段7：元层健康度与跨链路一致性（对应文档「附A 阶段7」、「十七」）。

覆盖数据契约：
  - 服务健康检查：/api/v1/system/health
  - 系统状态与路由初始化规格：/api/v1/system/status、/api/v1/route/init
  - OpenAPI 契约完整性：关键端点存在于 schema
  - 跨通道 L0 一致性：web 与 voice 对同一指令返回相同话术
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.test_02_routing import _create_routable_macro, _wait_for_macro_in_spec

from .conftest import VoiceConn

pytestmark = pytest.mark.e2e


async def _safe_macro(http_client: httpx.AsyncClient) -> str:
    """创建一个无副作用的 wait 宏（1ms）并等待其进入 L0 规格，返回 macro_id。

    ``_create_routable_macro`` 使用真实 trigger "麻烦对对对"；同名/同 trigger
    冲突时最新确认的宏优先，该 trigger 由调用方作为路由文本发送。
    """
    macro_id = await _create_routable_macro(http_client, "ack", "麻烦对对对")
    await _wait_for_macro_in_spec(http_client, macro_id)
    return macro_id


class TestServiceHealth:
    """阶段7-1 服务健康度。"""

    @pytest.mark.timeout(30)
    async def test_health_endpoint(self, http_client: httpx.AsyncClient) -> None:
        resp = await http_client.get("/api/v1/system/health")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "evoloop-backend"

    @pytest.mark.timeout(30)
    async def test_system_status_endpoint(self, http_client: httpx.AsyncClient) -> None:
        resp = await http_client.get("/api/v1/system/status")
        assert resp.status_code in (200, 401), resp.text

    @pytest.mark.timeout(30)
    async def test_route_init_spec(self, http_client: httpx.AsyncClient) -> None:
        """路由初始化规格接口可访问（导航宏预设数据契约的源头）。"""
        resp = await http_client.get("/api/v1/route/init")
        assert resp.status_code in (200, 202), resp.text
        if resp.status_code == 200:
            assert "version" in resp.json()

    @pytest.mark.timeout(30)
    async def test_openapi_schema_contract(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """OpenAPI 暴露全部关键链路端点。"""
        resp = await http_client.get("/api/v1/openapi.json")
        assert resp.status_code == 200, resp.text
        paths = resp.json().get("paths", {})
        for expected in (
            "/api/v1/chat",
            "/api/v1/chat/stop",
            "/api/v1/chat/retry",
            "/api/v1/stream/chat/{thread_id}",
            "/api/v1/files/upload",
            "/api/v1/system/health",
        ):
            assert expected in paths, f"OpenAPI 缺少端点: {expected}"


class TestCrossLinkConsistency:
    """阶段7-2 跨链路契约一致性（本序汇总校验）。"""

    @pytest.mark.timeout(60)
    async def test_l0_phrase_consistent_across_channels(
        self,
        http_client: httpx.AsyncClient,
        voice_conn: VoiceConn,
        thread_id: str,
    ) -> None:
        """同一 L0 宏指令（"麻烦对对对"）在 web 与 voice 通道返回相同话术（"完成"）。"""
        macro_id = await _safe_macro(http_client)
        try:
            web_resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": "麻烦对对对", "project_id": 0},
            )
            assert web_resp.status_code == 200, web_resp.text
            web_body = web_resp.json()
            assert web_body["status"] == "done"
            assert web_body["summary"] == "完成"

            await voice_conn.send_route("麻烦对对对")
            voice_env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert voice_env["body"]["status"] == "done"
            assert voice_env["body"]["summary"] == "完成", (
                f"跨通道话术不一致: web={web_body['summary']!r} "
                f"voice={voice_env['body']['summary']!r}"
            )
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(60)
    async def test_voice_envelope_is_canonical(
        self, http_client: httpx.AsyncClient, voice_conn: VoiceConn
    ) -> None:
        """语音链路所有下发行消息均为 canonical 信封（链路收口一致性）。"""
        macro_id = await _safe_macro(http_client)
        try:
            await voice_conn.send_route("麻烦对对对")
            env = await voice_conn.wait_terminal_route_result(timeout=20.0)
            assert env["version"] == "2.0"
            assert isinstance(env["message_id"], str)
            assert isinstance(env["timestamp"], int)
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")
