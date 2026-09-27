"""阶段5：持久化与异步闭环端到端测试（对应文档「附A 阶段5」、「十二」）。

覆盖数据契约：
  - 入站消息落库：/chat 后 messages 历史包含 human 消息
  - 会话列表与重命名：/conversations 增查改
  - 云同步前置：本地 sync 契约（sync_status 标记由服务端维护，此处验证本地侧持久化闭环）
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from .conftest import observe_agent_run, verify_quota_exhausted_feedback, wait_until

pytestmark = pytest.mark.e2e


class TestMessagePersistence:
    """十二 会话消息持久化。"""

    @pytest.mark.timeout(60)
    async def test_human_message_persisted(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """dispatch_agent_run 同步落库 human 消息，接口可立即查到。"""
        text = "帮我分析一下项目里的核心模块依赖"
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": text}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        persisted_message_id = body["message_id"]

        async def _check() -> list[dict]:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/messages")
            assert resp.status_code == 200, resp.text
            return [
                m
                for m in resp.json().get("data", [])
                if m.get("role") == "human" and m.get("id") == persisted_message_id
            ]

        messages = await wait_until(_check, timeout=20.0, desc="human 消息落库")
        assert messages[0]["content"] == text

    @pytest.mark.timeout(180)
    async def test_messages_history_readable_after_run(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """真实 LLM 运行跑完后，消息历史读取路径（归一化）保持可用且包含 AI 回复。"""
        text = "你好，请确认消息历史读取链路正常。"
        observer_task = asyncio.create_task(
            observe_agent_run(
                http_client, thread_id, timeout=150.0, expect_start=False
            )
        )
        await asyncio.sleep(0)  # 预订阅 SSE，避免 run_start 丢弃

        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": text}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        result = await observer_task
        resp = await http_client.get(f"/api/v1/conversations/{thread_id}/messages")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        data = body.get("data", [])
        assert isinstance(data, list)

        if result.run_end_status == "quota_exhausted":
            verify_quota_exhausted_feedback(result.all_events)
            assert body.get("total_count", 0) >= 1, (
                f"配额耗尽后至少应保留 human 消息，total_count={body.get('total_count')}"
            )
            roles = [m.get("role") for m in data]
            assert "human" in roles, f"历史消息中缺少 human 消息: {roles}"
            return

        assert body.get("total_count", 0) >= 2, (
            f"真实运行后应至少包含 human+ai 消息，total_count={body.get('total_count')}"
        )
        roles = [m.get("role") for m in data]
        assert "human" in roles, f"历史消息中缺少 human 消息: {roles}"
        assert "ai" in roles, f"历史消息中缺少 ai 回复: {roles}"
        human = next(m for m in data if m.get("role") == "human")
        assert human.get("content") == text


class TestConversationPersistence:
    """十二 会话元数据（列表/重命名）。"""

    @pytest.mark.timeout(60)
    async def test_conversation_listed(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """创建会话后出现在 /conversations 列表中。"""
        await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "你好"}
        )
        resp = await http_client.get(
            "/api/v1/conversations/", params={"page_size": 100}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("data", [])
        assert any(item["thread_id"] == thread_id for item in items), (
            f"会话 {thread_id} 未出现在列表中"
        )

    @pytest.mark.timeout(60)
    async def test_conversation_rename_persisted(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """PATCH 重命名会话 → 更新成功且列表可读回新标题。"""
        await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "重命名测试"}
        )
        new_title = "E2E 重命名会话标题"
        resp = await http_client.patch(
            f"/api/v1/conversations/{thread_id}", json={"title": new_title}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "updated"
        assert body["title"] == new_title

        list_resp = await http_client.get(
            "/api/v1/conversations/", params={"page_size": 100}
        )
        items = list_resp.json().get("data", [])
        match = next((item for item in items if item["thread_id"] == thread_id), None)
        assert match is not None
        assert match["title"] == new_title

    @pytest.mark.timeout(60)
    async def test_conversation_delete(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """删除会话 → 返回 deleted 契约。"""
        await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "删除测试"}
        )
        resp = await http_client.delete(f"/api/v1/conversations/{thread_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "deleted"


class TestMessagePersistenceEdgeCases:
    """十二 持久化边界场景。"""

    @pytest.mark.timeout(120)
    async def test_rewind_to_first_message_twice(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """倒带到首消息后再次倒带同一 message_id，应返回 404 而非 500。"""
        await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "第一轮问题"}
        )
        msgs = await wait_until(
            lambda: http_client.get(f"/api/v1/conversations/{thread_id}/messages"),
            timeout=20.0,
            desc="首轮消息落库",
        )
        msgs.raise_for_status()
        human = next(m for m in msgs.json()["data"] if m["role"] == "human")

        resp1 = await http_client.post(
            f"/api/v1/conversations/{thread_id}/rewind",
            json={"message_id": human["id"]},
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["status"] == "rewound"

        resp2 = await http_client.post(
            f"/api/v1/conversations/{thread_id}/rewind",
            json={"message_id": human["id"]},
        )
        # 回归防线是"不 500"：include_target=True 时 target 已随首次倒带删除，
        # 第二次按当前实现返回 404；若未来实现改为幂等语义则返回 200/rewound。
        assert resp2.status_code in (200, 404), resp2.text
        if resp2.status_code == 200:
            assert resp2.json().get("removed_count", 0) == 0, (
                f"重复倒带应不再删除消息: {resp2.text}"
            )

    @pytest.mark.timeout(120)
    async def test_delete_conversation_while_running_does_not_crash(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """运行中删除会话不应导致 500（可能 200 或 409 busy）。"""
        # 启动一个大概率会持续运行一段时间的复杂任务
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我做一个深度代码调研并给出详细报告"},
        )
        # 不等运行结束，直接删除
        resp = await http_client.delete(f"/api/v1/conversations/{thread_id}")
        assert resp.status_code in (200, 409), (
            f"运行中删除会话不应 500，实际: {resp.status_code} {resp.text[:200]}"
        )
        if resp.status_code == 200:
            assert resp.json()["status"] in ("deleted", "busy")
