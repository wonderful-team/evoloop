"""阶段3：Agent 引擎执行端到端测试（对应文档「附A 阶段3」）。

覆盖数据契约（全部为真实链路，不使用 mock 场景）：
  - 真实 Agent 运行（单 Agent ReAct 循环）终态事件链：run_start → run_end
  - 完整流式事件链：run_start → (thinking/token/message/progress) → run_end(done)
  - 运行终态后活动状态流转闭环（activity 不再是 running）
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from .conftest import (
    collect_sse_until,
    observe_agent_run,
    verify_quota_exhausted_feedback,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
async def unique_marker() -> str:
    """生成唯一标记，用于在真实命令副作用中识别测试痕迹。"""
    return f"e2e-real-{uuid.uuid4().hex[:8]}"


class TestRealAgentRun:
    """四/五 真实 Agent 引擎执行 + 审计（依赖 LLM 网关，验证契约而非内容）。"""

    @pytest.mark.timeout(180)
    async def test_real_run_end_to_end_contract(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """L1 委托 → run_start → ... → run_end 终态信封（done/failed/cancelled 均合法）。"""
        # 先启动 SSE 观测任务，再触发 chat，避免 run_start 在订阅建立前已发布而丢失。
        observer_task = asyncio.create_task(
            observe_agent_run(
                http_client, thread_id, timeout=150.0, expect_start=False
            )
        )
        await asyncio.sleep(0)  # 让观测任务先开始连接 SSE

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "帮我整理一下今天的工作计划",
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        result = await observer_task
        assert result.run_end is not None
        status = result.run_end_status
        assert status in (
            "done",
            "failed",
            "cancelled",
            "quota_exhausted",
        ), f"run_end 终态字段异常: {result.run_end.json}"
        # 正常完成链路必须发送 run_start；若因配额/异常快速失败则允许缺失
        if status == "done":
            assert result.run_start is not None, (
                f"done 终态前未收到 run_start，thread={thread_id}"
            )

    @pytest.mark.timeout(240)
    async def test_real_run_full_event_chain(
        self, http_client: httpx.AsyncClient, thread_id: str, unique_marker: str
    ) -> None:
        """真实运行完整事件链：run_start → token/message/progress → run_end(done)。

        工具型提示词保证触发 on_tool_start，从而真实链路必须发出 progress 事件；
        token 由 LLM 流式回调（TransparentCallbackHandler）批量发布，message 为消息块同步事件。
        """
        event_names: list[str] = []

        async def _on_event(ev: object) -> None:
            event_names.append(getattr(ev, "event", ""))

        observer_task = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                on_event=_on_event,
                desc="真实完整事件链 run_end",
            )
        )
        await asyncio.sleep(0)  # 预订阅：确保 run_start 之前建立 SSE 连接

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请使用 execute_command 工具运行命令 `echo chain-{unique_marker}`，"
                    "并返回命令输出。"
                ),
                "project_id": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        events = await observer_task
        run_end = next(ev for ev in events if ev.event == "run_end").json
        status = run_end.get("status")
        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        if status in ("failed", "quota_exhausted", "cancelled"):
            pytest.fail(
                f"真实运行未正常完成，status={status}, run_end={run_end}, "
                f"event_names={event_names}"
            )
        assert status == "done", f"run_end 应为 done，实际: {run_end}"

        assert "run_start" in event_names, (
            f"done 终态前未收到 run_start，实际事件: {event_names}"
        )
        assert "token" in event_names, f"缺少 token 流式事件: {event_names}"
        assert "message" in event_names, f"缺少 message 块事件: {event_names}"
        assert "progress" in event_names, f"缺少 progress 事件: {event_names}"

    @pytest.mark.timeout(120)
    async def test_run_end_persisted_activity(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """真实运行终态后，活动状态可查询且不再是 running（四 状态流转闭环）。"""
        observer_task = asyncio.create_task(
            observe_agent_run(
                http_client, thread_id, timeout=120.0, expect_start=False
            )
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "你好，请确认链路正常"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        await observer_task
        resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
        assert resp.status_code == 200, resp.text
        state = resp.json()
        assert state is not None
        assert state.get("status") in (
            "done",
            "failed",
            "cancelled",
            "idle",
            "quota_exhausted",
        )


    @pytest.mark.timeout(120)
    async def test_quota_exhausted_feedback_to_frontend(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """配额耗尽时，必须向前端推送 quota_exhausted 事件并携带可读消息。"""
        observer_task = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=120.0,
                desc="quota_exhausted feedback events",
            )
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "你好", "project_id": 0},
        )
        assert resp.status_code == 200, resp.text

        events = await observer_task
        run_end = next(ev.json for ev in events if ev.event == "run_end")
        status = run_end.get("status")
        if status != "quota_exhausted":
            pytest.skip("当前运行未触发配额耗尽，跳过前端反馈专项验证")

        for ev in events:
            print(f"[{ev.event}] {ev.data[:500]}")

        quota_events = [ev for ev in events if ev.event == "quota_exhausted"]
        assert quota_events, "配额耗尽时未收到 quota_exhausted SSE 事件"
        quota_data = quota_events[0].json
        assert quota_data.get("message"), (
            f"quota_exhausted 事件缺少可读消息: {quota_data}"
        )
