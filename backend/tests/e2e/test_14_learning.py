"""阶段：学习与宏演化端到端测试。

覆盖：
  - E2E-SC-017：演化出的宏可通过 web 和 voice 双通道触发

注：自动宏沉淀机制（SESSION_COMPLETED 后自动生成宏）已移除，待重新设计。
    当前仅验证人工创建并确认后的宏可跨通道触发。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import wait_until

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# 宏 API 辅助
# ---------------------------------------------------------------------------


async def _create_routable_macro(http_client: httpx.AsyncClient, trigger: str) -> int:
    """创建并确认一个最小可路由宏（wait 1ms），返回 macro_id。"""
    script = "- type: action\n  event_type: wait\n  payload:\n    duration_ms: 1\n"
    create_resp = await http_client.post(
        "/api/v1/macros/",
        json={
            "name": f"e2e-cross-{uuid.uuid4().hex[:8]}",
            "description": "cross-channel evolved macro",
            "macro_script": script,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    macro_id = create_resp.json()["id"]

    update_resp = await http_client.put(
        f"/api/v1/macros/{macro_id}",
        json={"trigger_patterns": [trigger]},
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    return macro_id


async def _wait_for_macro_in_spec(
    http_client: httpx.AsyncClient, macro_id: int, timeout: float = 60.0
) -> None:
    """轮询 /route/init 直到宏触发器被载入 L0 规格。"""

    async def _check() -> bool:
        resp = await http_client.get("/api/v1/route/init")
        if resp.status_code != 200:
            return False
        data = resp.json()
        templates = data.get("templates", [])
        return any(t.get("action") == f"macro:{macro_id}" for t in templates)

    await wait_until(_check, timeout=timeout, desc=f"L0 spec 载入 macro:{macro_id}")


class TestEvolvedMacroChannels:
    """E2E-SC-017：演化出的宏可通过 web 和 voice 双通道触发。"""

    @pytest.mark.timeout(120)
    async def test_evolved_macro_runs_on_web_and_voice(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        voice_conn: Any,
    ) -> None:
        """创建并确认一个宏，等待 L0 缓存刷新，分别在 HTTP 和 voice 触发。"""
        trigger = f"e2e跨通道测试{uuid.uuid4().hex[:6]}"
        macro_id = await _create_routable_macro(http_client, trigger)

        try:
            await _wait_for_macro_in_spec(http_client, macro_id, timeout=60.0)

            # 1. Web 通道触发。
            web_resp = await http_client.post(
                "/api/v1/chat",
                json={
                    "thread_id": thread_id,
                    "message": trigger,
                    "project_id": 0,
                },
            )
            assert web_resp.status_code == 200, web_resp.text
            web_body = web_resp.json()
            assert web_body["status"] == "done", f"Web 宏触发未返回 done: {web_body}"
            assert web_body["action_type"] == "macro", (
                f"Web 宏触发 action_type 不是 macro: {web_body}"
            )
            assert web_body["thread_id"] == thread_id

            # 2. Voice 通道触发。
            await voice_conn.send_route(trigger)
            voice_env = await voice_conn.wait_terminal_route_result(timeout=30.0)
            assert voice_env["body"]["status"] == "done", (
                f"Voice 宏触发未返回 done: {voice_env}"
            )
            # Voice 终态信封中 action_type 字段可能不存在，若存在则校验。
            if "action_type" in voice_env["body"]:
                assert voice_env["body"]["action_type"] == "macro", (
                    f"Voice 宏触发 action_type 不是 macro: {voice_env}"
                )
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")
