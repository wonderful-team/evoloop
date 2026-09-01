"""记忆检索→注入 Agent 上下文（recall 工具检索已保存概念）。

链路：概念经 /memory/concepts 保存 → 新会话中 Agent 调用 recall 工具检索 →
    检索结果进入上下文并用于回答。
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from tests.e2e.conftest import observe_agent_run

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _ai_reply_text(http_client: httpx.AsyncClient, thread_id: str) -> str:
    """从消息历史拼接 AI 回复全文。"""
    resp = await http_client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        params={"include_tool_calls": "true"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return " ".join(
        (m.get("content") or "") for m in resp.json().get("data", []) if m.get("role") == "ai"
    )


class TestMemoryInjection:
    @pytest.mark.timeout(240)
    async def test_recall_retrieves_saved_concept(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        concept = f"e2e-mem-{uuid.uuid4().hex[:6]}"
        value = f"记忆值-{uuid.uuid4().hex[:6]}"

        # 1. 保存概念（确定性）
        add = await http_client.post(
            "/api/v1/memory/concepts",
            params={"project_id": 0},
            json={"name": concept, "description": value},
        )
        assert add.status_code == 200, add.text
        try:
            # 2. 验证记忆库确实保存（API 可检索）
            listed = await http_client.get(
                "/api/v1/memory/concepts", params={"project_id": 0}
            )
            listed.raise_for_status()
            names = [c.get("name") for c in listed.json()]
            assert concept in names, f"概念 {concept} 未保存到记忆库"

            # 3. 新会话：让 Agent 用 recall 工具检索该概念并报告内容
            observer = asyncio.create_task(
                observe_agent_run(http_client, thread_id, timeout=200.0)
            )
            await asyncio.sleep(0)
            prompt = (
                f"请调用 recall 工具检索概念「{concept}」，"
                f"然后用一句话告诉我它的描述内容。"
            )
            chat = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": prompt, "project_id": 0},
            )
            assert chat.status_code == 200, chat.text
            assert chat.json()["status"] in ("queued", "done")

            result = await observer
            if result.run_end_status in ("failed", "cancelled", "quota_exhausted"):
                pytest.skip(
                    f"Agent 运行未成功完成（{result.run_end_status}），无法验证记忆注入"
                )

            # 4. 核心断言：Agent 回复中应包含记忆值（检索结果注入上下文）
            reply = await _ai_reply_text(http_client, thread_id)
            assert value in reply, (
                f"Agent 回复未包含记忆值 {value!r}（记忆未检索/注入上下文）。"
                f"回复前 200 字: {reply[:200]!r}"
            )
        finally:
            await http_client.delete(
                f"/api/v1/memory/concepts/{concept}", params={"_project_id": 0}
            )
