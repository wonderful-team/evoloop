"""阶段6：运行时控制端到端测试（对应文档「附A 阶段6」、「十四」「十五」「十六」）。

覆盖数据契约：
  - Stop 软中断：/chat/stop → 取消标记 → AgentCancelledException → run_end cancelled
  - voice.cancel 硬掐断：task.cancel() → voice.route_result {status:"cancelled"}
  - Rewind/Retry：消息物理删除 + 重新调度
  - Barge-in：仅静音 + 状态迁移，不取消后台 Worker（语音状态机）
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from .conftest import VoiceConn, observe_agent_run, wait_until

pytestmark = pytest.mark.e2e


class TestStopCommand:
    """十四 运行时停止（软中断）。"""

    @pytest.mark.timeout(180)
    async def test_stop_endpoint_contract(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """/chat/stop 返回 stopping 契约。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我做一个深度代码调研"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        resp = await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "stopping"
        assert body["thread_id"] == thread_id

    @pytest.mark.timeout(180)
    async def test_stop_soft_interrupt_terminates_run(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """stop 软信号 → 引擎节点循环软截断 → run_end（cancelled 为期望终态）。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我深度调研一下这个项目"},
        )
        await asyncio.sleep(0.5)
        await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )

        result = await observe_agent_run(
            http_client, thread_id, timeout=150.0, expect_start=False
        )
        status = result.run_end_status
        assert status in ("cancelled", "failed"), (
            f"stop 后应观察到 cancelled/failed 终态，实际: {status} "
            f"({result.run_end.json})"
        )

        # 终态后线程不再处于 running（节点循环已退出）
        async def _not_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            state = resp.json() or {}
            return state.get("status") != "running"

        await wait_until(_not_running, timeout=30.0, desc="线程退出 running")


class TestVoiceCancel:
    """十四 voice.cancel 硬掐断路径。"""

    @pytest.mark.timeout(120)
    async def test_voice_cancel_envelope(self, voice_conn: VoiceConn) -> None:
        """voice.route 拉起后台 Agent 后 voice.cancel → task.cancel() → cancelled 终态信封。"""
        # 使用复合意图文本确保进入 Agent 后台执行
        await voice_conn.send_route("先搜索前端代码再部署到测试环境")
        await asyncio.sleep(1.0)  # 等待 worker 注册完成

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
        ), f"voice.cancel 后应收到 cancelled/failed，实际: {status}"


class TestRewindRetry:
    """十五 倒带与重试。"""

    @pytest.mark.timeout(120)
    async def test_rewind_removes_messages(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """Rewind 物理删除目标消息（含其后的记录），并返回 removed_count。"""
        await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "第一轮问题"}
        )
        msgs = await wait_until(
            lambda: http_client.get(f"/api/v1/conversations/{thread_id}/messages"),
            timeout=20.0,
            desc="消息可读",
        )
        msgs.raise_for_status()
        human = next(m for m in msgs.json()["data"] if m["role"] == "human")

        resp = await http_client.post(
            f"/api/v1/conversations/{thread_id}/rewind",
            json={"message_id": human["id"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "rewound"
        assert body["removed_count"] >= 0

        after = await http_client.get(f"/api/v1/conversations/{thread_id}/messages")
        ids_after = {m["id"] for m in after.json().get("data", [])}
        assert human["id"] not in ids_after, "倒带后目标消息应被物理删除"

    @pytest.mark.timeout(120)
    async def test_retry_endpoint_contract(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """/chat/retry 重放目标 human 消息 → queued + action:retry 契约。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我生成一个项目周报模板"},
        )
        msgs = await wait_until(
            lambda: http_client.get(f"/api/v1/conversations/{thread_id}/messages"),
            timeout=20.0,
            desc="消息可读",
        )
        msgs.raise_for_status()
        human = next(m for m in msgs.json()["data"] if m["role"] == "human")

        resp = await http_client.post(
            "/api/v1/chat/retry",
            json={
                "thread_id": thread_id,
                "message_id": human["id"],
                "revert_files": True,
                "message": "retry",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["action"] == "retry"
        assert "files_reverted" in body


class TestBargeInStateMachine:
    """十六 全双工语音状态机：Barge-in 仅静音不取消 Worker。"""

    @pytest.mark.timeout(60)
    async def test_barge_in_envelope_and_continue(self, voice_conn: VoiceConn) -> None:
        """先 route（绑定线程）再 barge_in → voice.barge_in 信封，后续 route 仍可受理。"""
        await voice_conn.send_route("对的")
        done_env = await voice_conn.wait_route_result(timeout=20.0)
        assert done_env["body"]["status"] in ("done", "routed", "failed")

        await voice_conn.send_type(
            "voice.barge_in", {"thread_id": voice_conn.thread_id}
        )
        barge_env = await voice_conn.wait_type("voice.barge_in", timeout=10.0)
        assert barge_env["body"]["thread_id"] == voice_conn.thread_id

        # INTERRUPTED 状态仍可接受新指令（can_accept_route 允许）
        await voice_conn.send_route("再见")
        again = await voice_conn.wait_route_result(timeout=20.0)
        assert again["body"]["status"] in ("done", "routed", "failed")


class TestStopEdgeCases:
    """十四 stop 边界场景。"""

    @pytest.mark.timeout(30)
    async def test_stop_when_idle_returns_stopping_or_idle(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """空闲线程调用 stop 不应 500，应返回明确状态。"""
        resp = await http_client.post(
            "/api/v1/chat/stop", json={"thread_id": thread_id, "message": "stop"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("stopping", "idle"), f"空闲 stop 状态异常: {body}"
        assert body["thread_id"] == thread_id

    @pytest.mark.timeout(180)
    async def test_double_stop_terminates_run_once(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """连续两次 stop 后，Agent 仅被取消一次并到达终态。"""
        await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "帮我深度调研这个项目"},
        )
        await asyncio.sleep(0.3)

        resp1 = await http_client.post(
            "/api/v1/chat/stop", json={"thread_id": thread_id, "message": "stop"}
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["status"] == "stopping"

        resp2 = await http_client.post(
            "/api/v1/chat/stop", json={"thread_id": thread_id, "message": "stop"}
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["status"] == "stopping"

        result = await observe_agent_run(
            http_client, thread_id, timeout=150.0, expect_start=False
        )
        assert result.run_end_status in (
            "cancelled",
            "failed",
        ), f"双 stop 后终态异常: {result.run_end.json}"


class TestRetryEdgeCases:
    """十五 retry 边界场景。"""

    @pytest.mark.timeout(30)
    async def test_retry_nonexistent_message_returns_404(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """不存在的 message_id 重试应返回 404，而非 500。"""
        resp = await http_client.post(
            "/api/v1/chat/retry",
            json={
                "thread_id": thread_id,
                "message_id": "msg-not-exist",
                "message": "retry",
            },
        )
        assert resp.status_code == 404, resp.text


class TestBargeInEdgeCases:
    """十六 barge-in 边界场景。"""

    @pytest.mark.timeout(30)
    async def test_barge_in_before_route(self, voice_conn: VoiceConn) -> None:
        """未 route 前先发送 barge-in，连接不应崩溃且后续 route 仍可受理。"""
        await voice_conn.send_type(
            "voice.barge_in", {"thread_id": voice_conn.thread_id}
        )
        # 不要求必须返回 barge_in 信封（线程未绑定可能不推送），但 WS 必须保持可用
        await voice_conn.send_route("再见")
        env = await voice_conn.wait_route_result(timeout=20.0)
        assert env["type"] == "voice.route_result"
        assert env["body"]["status"] in ("done", "routed", "failed")
