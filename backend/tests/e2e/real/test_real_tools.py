"""真实工具执行 E2E 测试。

通过 `/api/v1/chat` 发送明确会触发工具调用的提示，观察真实 Agent 是否：
1. 在 SSE 中发出工具调用（role=ai, tool_calls）
2. 在 SSE 中收到真实工具输出（role=tool, tool_name=...）
3. 最终 run_end 到达 done 状态
4. 副作用（文件/命令输出）确实发生

参数化覆盖：正常命令、文件读写、失败命令、危险命令被拦截。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    SSEEmitter,
    collect_sse_until,
    verify_quota_exhausted_feedback,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _run_chat_with_tools(
    http_client: httpx.AsyncClient,
    thread_id: str,
    prompt: str,
    project_id: int = 0,
    timeout: float = 180.0,
    auto_cancel_hitl: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[SSEEmitter]]:
    """发起 chat，收集 SSE 直到 run_end，返回所有 MessageBlock 列表、run_end 数据与完整事件列表。"""
    resp = await http_client.post(
        "/api/v1/chat",
        json={
            "thread_id": thread_id,
            "message": prompt,
            "project_id": project_id,
        },
    )
    assert resp.status_code == 200, f"/chat 入口失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("status") == "queued", f"/chat 应返回 queued: {data}"

    on_event = await _make_hitl_cancel_handler(http_client, thread_id) if auto_cancel_hitl else None
    events = await collect_sse_until(
        http_client,
        f"/api/v1/stream/chat/{thread_id}",
        lambda ev: ev.event == "run_end",
        timeout=timeout,
        desc=f"run_end for prompt: {prompt[:40]!r}",
        on_event=on_event,
    )
    run_end = next((ev.json for ev in events if ev.event == "run_end"), {})
    messages = [
        ev.json.get("data", {})
        for ev in events
        if ev.event == "message" and isinstance(ev.json, dict) and ev.json.get("data")
    ]
    return messages, run_end, events


def _find_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从消息列表中提取 AI 发出的工具调用。"""
    calls: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "ai":
            continue
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                calls.append(tc)
    return calls


def _find_tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从消息列表中提取工具输出块。"""
    return [
        msg
        for msg in messages
        if msg.get("role") == "tool" and msg.get("tool_name")
    ]


def _content_or_meta_contains(msg: dict[str, Any], needle: str) -> bool:
    """检查工具输出 content 或 meta_data 中是否包含目标字符串。"""
    content = msg.get("content") or ""
    if needle in content:
        return True
    meta = msg.get("meta_data") or {}
    for value in meta.values():
        if isinstance(value, str) and needle in value:
            return True
        if isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, str) and needle in inner:
                    return True
    return False


async def _make_hitl_cancel_handler(
    http_client: httpx.AsyncClient,
    thread_id: str,
) -> Callable[[SSEEmitter], Awaitable[None]]:
    """构造 SSE 副作用回调：收到 human_request 时自动取消 HITL 请求。"""
    cancelled = False

    async def _on_event(ev: SSEEmitter) -> None:
        nonlocal cancelled
        if cancelled or ev.event != "human_request":
            return

        data = ev.json
        request_type = data.get("request_type") or data.get("type")
        if request_type not in ("approval", "confirmation", "text", "choice"):
            return

        resp = await http_client.post(
            "/api/v1/hitl/cancel",
            json={"thread_id": thread_id, "reason": "e2e auto-cancel"},
        )
        if resp.status_code == 200:
            cancelled = True
            logger.info("已自动取消 thread=%s 的 HITL 请求", thread_id)
        else:
            logger.warning(
                "自动取消 HITL 请求失败 thread=%s: %s %s",
                thread_id,
                resp.status_code,
                resp.text[:200],
            )

    return _on_event


class TestRealToolExecution:
    """真实工具执行闭环。"""

    @pytest.mark.timeout(240)
    @pytest.mark.parametrize(
        "prompt_template, expected_tool, expected_marker, expect_blocked",
        [
            (
                "请使用 execute_command 工具运行命令 `echo hello-e2e-{marker}`，并返回完整输出。",
                "execute_command",
                "hello-e2e-{marker}",
                False,
            ),
            (
                "请使用 write_file 工具创建文件 `e2e-real-{marker}.txt`，内容写入 `write-e2e-{marker}`，"
                "然后用 read_file 读取该文件验证内容。",
                "write_file",
                "write-e2e-{marker}",
                False,
            ),
            pytest.param(
                "请使用 execute_command 工具运行命令 `exit 1`，观察非零退出码。",
                "execute_command",
                "Exit Code 1",
                False,
                id="failed-command",
            ),
            pytest.param(
                "请使用 execute_command 工具运行命令 `rm -rf /`，观察安全拦截。",
                "execute_command",
                "Security Error",
                True,
                id="dangerous-command-blocked",
            ),
        ],
    )
    async def test_real_tool_run_via_agent(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,
        prompt_template: str,
        expected_tool: str,
        expected_marker: str,
        expect_blocked: bool,
    ) -> None:
        """Agent 真实调用工具并产生可观测副作用。"""
        prompt = prompt_template.format(marker=unique_marker)
        messages, run_end, events = await _run_chat_with_tools(
            http_client, thread_id, prompt, timeout=240.0, auto_cancel_hitl=expect_blocked
        )

        status = run_end.get("status")
        logger.info(
            "thread=%s run_end=%s messages=%d",
            thread_id,
            status,
            len(messages),
        )

        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        # 配额/认证类失败也要记录为缺陷，但先给出明确断言
        if status in ("failed", "cancelled"):
            pytest.fail(
                f"Agent 运行未正常完成，status={status}, run_end={run_end}, prompt={prompt[:60]!r}"
            )

        # 危险命令场景：安全层阻止或 HITL 取消后被打断都属于“未实际执行”的通过状态。
        if expect_blocked:
            assert status in (
                "done",
                "human_interrupt",
            ), f"run_end 终态应为 done/human_interrupt，实际: {run_end}"
        else:
            assert status == "done", f"run_end 终态应为 done，实际: {run_end}"

        tool_calls = _find_tool_calls(messages)
        tool_outputs = _find_tool_outputs(messages)

        # 至少有一次目标工具调用
        matching_calls = [tc for tc in tool_calls if tc.get("name") == expected_tool]

        if expect_blocked:
            # 安全拦截场景：允许未发起工具调用（已被安全层拒绝），
            # 也允许工具调用被拦截后输出包含 Security Error
            if not matching_calls:
                logger.info(
                    "危险命令被安全层阻止，未发起 %s 调用", expected_tool
                )
                return

        assert matching_calls, (
            f"未在 SSE 中发现 {expected_tool} 工具调用，tool_calls={tool_calls}"
        )

        # 至少有一次工具输出包含期望标记
        found_marker = any(
            _content_or_meta_contains(out, expected_marker.format(marker=unique_marker))
            for out in tool_outputs
        )
        assert found_marker, (
            f"工具输出中未包含期望标记 {expected_marker!r}, "
            f"tool_outputs={json.dumps(tool_outputs, ensure_ascii=False)[:500]}"
        )

    @pytest.mark.timeout(180)
    async def test_real_file_side_effect(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        unique_marker: str,
        temp_project: dict[str, Any],
    ) -> None:
        """Agent 调用 write_file 后，磁盘上确实存在目标文件（落在绑定项目目录内）。

        /chat 对 project_id=0 走全局 active project（SSOT），落盘位置随机器状态漂移；
        这里通过 temp_project 显式绑定新项目，使工作目录确定为该项目目录。
        """
        if not temp_project.get("imported") or not temp_project.get("project_id"):
            pytest.skip("临时项目导入失败，无法确定 write_file 落盘目录")

        project_id = temp_project["project_id"]
        project_dir = Path(temp_project["path"])
        target_file = f"e2e-real-{unique_marker}.txt"
        prompt = (
            f"请使用 write_file 工具创建文件 `{target_file}`，"
            f"内容写入 `side-effect-{unique_marker}`。"
        )
        messages, run_end, events = await _run_chat_with_tools(
            http_client, thread_id, prompt, project_id=project_id, timeout=180.0
        )

        status = run_end.get("status")
        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(events)
            return

        if status != "done":
            pytest.fail(
                f"文件副作用测试失败，run_end={status}, run_end_data={run_end}"
            )

        expected_path = project_dir / target_file
        # 给文件系统一点写入时间，但通常应在 run_end 前完成
        for _ in range(50):
            if expected_path.exists():
                break
            await asyncio.sleep(0.1)

        assert expected_path.exists(), (
            f"write_file 工具未在磁盘创建文件: {expected_path}"
        )
        content = expected_path.read_text(encoding="utf-8")
        assert f"side-effect-{unique_marker}" in content, (
            f"文件内容不匹配: {content[:200]!r}"
        )
