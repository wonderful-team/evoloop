"""Web 宏 self-healing 自愈回退（execution/macro/runner.py WEB_POLICY）。

web 源宏执行失败（bash exit 1）时，WebPolicy(allow_self_heal=True) 应触发
MacroService 自愈 → Agent 恢复，响应标记 fell_back=True。
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.test_02_routing import _create_failing_macro, _wait_for_macro_in_spec

pytestmark = [pytest.mark.e2e, pytest.mark.real]


class TestWebMacroSelfHeal:
    @pytest.mark.timeout(120)
    async def test_failing_web_macro_falls_back(self, http_client: httpx.AsyncClient, thread_id: str) -> None:
        """web 源触发必然失败的宏 → 自愈回退（fell_back=True）。"""
        macro_id = await _create_failing_macro(http_client, "ack", "麻烦对对对")
        try:
            await _wait_for_macro_in_spec(http_client, macro_id)
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": "麻烦对对对", "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            if body.get("action_type") == "macro":
                # 宏被 L0 命中并执行失败 → web self-healing 回退（fell_back=True），
                # 响应快速返回 failed（宏失败）但标记已自愈。
                assert body["status"] == "failed", f"宏失败应返回 failed: {body}"
                assert body.get("fell_back") is True, (
                    f"宏失败后应触发自愈回退（fell_back=True），实际: {body}"
                )
            else:
                # 若 L0 未命中（分类抖动）委托 Agent，也是一种合法兜底
                assert body["status"] in ("queued", "done")
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")
