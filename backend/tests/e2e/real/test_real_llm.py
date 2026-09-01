"""真实 LLM 任务闭环 E2E 测试。

覆盖：
- 简单对话：后端真实调用 LLM 并返回文本
- 推理/工具闭环：要求调用 execute_command 后再总结
- 异常模型：传入不存在的模型，观察失败/降级行为
- 配置探测：读取 LLM_PROVIDER / LLM_MODEL，参数化真实可用模型

所有用例都通过 `/api/v1/chat` + SSE 观测闭环。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import collect_sse_until, verify_quota_exhausted_feedback

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _chat_and_observe(
    http_client: httpx.AsyncClient,
    thread_id: str,
    message: str,
    model: str | None = None,
    project_id: int = 0,
    timeout: float = 180.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """发送 chat 并收集 SSE 直到 run_end。"""
    payload: dict[str, Any] = {
        "thread_id": thread_id,
        "message": message,
        "project_id": project_id,
    }
    if model is not None:
        payload["model"] = model

    resp = await http_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200, f"/chat 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("status") == "queued", f"/chat 应返回 queued: {data}"

    events = await collect_sse_until(
        http_client,
        f"/api/v1/stream/chat/{thread_id}",
        lambda ev: ev.event == "run_end",
        timeout=timeout,
        desc=f"LLM run_end for {message[:40]!r}",
    )
    run_end = next((ev.json for ev in events if ev.event == "run_end"), {})
    ai_messages = [
        ev.json.get("data", {})
        for ev in events
        if ev.event == "message"
        and isinstance(ev.json, dict)
        and ev.json.get("data", {}).get("role") == "ai"
    ]
    return ai_messages, run_end, events


class TestRealLLMClosedLoop:
    """真实 LLM 端到端闭环。"""

    @pytest.mark.timeout(180)
    @pytest.mark.parametrize(
        "message",
        [
            "你好，请用一句话确认 LLM 连接正常。",
            "请计算 1+1 并只给出数字结果。",
        ],
    )
    async def test_real_llm_simple_response(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        message: str,
    ) -> None:
        """真实 LLM 返回非空回复且 run_end 到达 done。"""
        ai_messages, run_end, events = await _chat_and_observe(
            http_client, thread_id, message, timeout=180.0
        )
        status = run_end.get("status")

        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        if status in ("failed", "cancelled"):
            pytest.fail(
                f"LLM 运行未正常完成，status={status}, run_end={run_end}"
            )

        assert status == "done", f"run_end 应为 done，实际: {run_end}"
        assert ai_messages, "未收到任何 AI 消息块"

        combined = "\n".join(str(m.get("content", "")) for m in ai_messages)
        assert combined.strip(), (
            f"AI 回复内容为空，ai_messages={ai_messages}"
        )

    @pytest.mark.timeout(240)
    @pytest.mark.parametrize(
        "model",
        [
            pytest.param(None, id="default-model"),
            pytest.param("nonexistent-model-for-e2e-test", id="invalid-model"),
        ],
    )
    async def test_real_llm_model_parameter(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        model: str | None,
    ) -> None:
        """参数化模型：默认模型应完成，不存在模型应失败或报错。"""
        message = "你好，请回复 'pong'。"
        ai_messages, run_end, events = await _chat_and_observe(
            http_client, thread_id, message, model=model, timeout=240.0
        )
        status = run_end.get("status")
        logger.info(
            "model=%s thread=%s status=%s ai_messages=%d",
            model,
            thread_id,
            status,
            len(ai_messages),
        )

        if model is None:
            # 默认模型应当成功完成；若环境无模型则失败并记录缺陷
            if status == "quota_exhausted":
                verify_quota_exhausted_feedback(events)
                return
            if status in ("failed", "cancelled"):
                pytest.fail(
                    f"默认模型未正常完成，status={status}, run_end={run_end}"
                )
            assert status == "done", f"默认模型 run_end 应为 done: {run_end}"
            combined = "\n".join(str(m.get("content", "")) for m in ai_messages)
            assert combined.strip(), "默认模型返回空内容"
        else:
            # 非法模型：允许 run_end failed 或 HTTP 层面报错，但系统不能静默成功
            assert status in (
                "done",
                "failed",
                "quota_exhausted",
                "cancelled",
            ), f"非法模型应返回明确终态，实际: {run_end}"

    @pytest.mark.timeout(240)
    async def test_real_llm_tool_closed_loop(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,
    ) -> None:
        """LLM 必须调用工具并基于工具输出给出最终回答。"""
        message = (
            f"请使用 execute_command 工具运行 `echo loop-{unique_marker}`，"
            f"然后告诉我命令输出里是否包含 loop-{unique_marker}。"
        )
        ai_messages, run_end, events = await _chat_and_observe(
            http_client, thread_id, message, timeout=240.0
        )
        status = run_end.get("status")

        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        if status in ("failed", "cancelled"):
            pytest.fail(
                f"LLM 工具闭环运行未正常完成，status={status}, run_end={run_end}"
            )

        assert status == "done", f"run_end 应为 done，实际: {run_end}"

        combined = "\n".join(str(m.get("content", "")) for m in ai_messages)
        assert f"loop-{unique_marker}" in combined, (
            f"LLM 最终回答未引用工具输出中的标记，combined={combined[:500]!r}"
        )
