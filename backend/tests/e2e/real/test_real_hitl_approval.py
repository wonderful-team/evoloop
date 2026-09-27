"""HITL 审批 → 工具重新注入执行闭环（真实 e2e）。

链路：非零 project_id 下，Agent 写入工作区外的敏感路径 → 授权门触发 HITL
（human_request）→ 审批（/chat/resume user_input=APPROVED）→ 工具被重新注入
并真正执行。

健壮性：LLM 可能改写路径，故从 write_file 工具调用的实际参数提取路径，
断言审批后该路径文件真实存在；且 HITL 审批确实发生过。
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.core.config import settings
from tests.e2e.conftest import SSEEmitter, collect_sse_until

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


@dataclass
class ApprovalState:
    hitl_seen: bool = False
    approved: bool = False
    request_types: list[str] = field(default_factory=list)


async def _make_approve_handler(
    http_client: httpx.AsyncClient,
    thread_id: str,
    state: ApprovalState,
) -> Any:
    """SSE 副作用回调：收到 HITL human_request 时发送 APPROVED 审批。

    同一轮运行可能触发多次审批（写/读各自独立授权），全部批准。
    """

    async def _on_event(ev: SSEEmitter) -> None:
        if ev.event != "human_request":
            return
        data = ev.json or {}
        request_type = data.get("request_type") or data.get("type")
        state.hitl_seen = True
        state.request_types.append(str(request_type))
        if request_type == "choice":
            # 模型自审鲁棒：LLM 可能不触发门控而是用 question 问人（实测网关
            # 默认模型会先问"是否改为写工作目录内"，且选项话术不固定）。
            # choice 属自由文本——无条件回传用户明确授权指令，让链路继续
            # 走到授权门 → 审批闭环。
            override = (
                "仍然写入 /tmp，用户明确授权该越界写入，必须执行，不要再询问"
            )
            resp = await http_client.post(
                "/api/v1/chat/resume",
                json={"thread_id": thread_id, "user_input": override},
            )
            if resp.status_code == 200:
                logger.info("[e2e] choice 已回传用户显式授权指令")
            return
        if request_type not in ("approval", "confirmation"):
            return
        resp = await http_client.post(
            "/api/v1/chat/resume",
            json={"thread_id": thread_id, "user_input": "APPROVED"},
        )
        if resp.status_code == 200:
            state.approved = True

    return _on_event


def _write_file_calls(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """从 AI 消息的 write_file 工具调用中提取 (path, content) 实际参数。

    以工具实际收到的参数为准，避免 LLM 改写/笔误 marker 导致断言失配。
    """
    calls: list[tuple[str, str]] = []
    for msg in messages:
        if msg.get("role") != "ai":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            if tc.get("name") != "write_file":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, dict) and args.get("path") and args.get("content"):
                calls.append((str(args["path"]), str(args["content"])))
    return calls


def _direct_target(target: str) -> str | None:
    """execute_command 直接把文件写在宿主机 /tmp（无重定向），存在即副作用证据。"""
    if os.path.exists(target):
        return target
    return None


def _find_landed_file(
    calls: list[tuple[str, str]], project_dir: str
) -> tuple[str, str] | None:
    """按 write_file 实际参数定位落盘文件（绝对路径会被重定向进工作目录）。

    返回 (落地文件路径, 写入内容)；找不到返回 None。
    """
    workspace_root = os.path.dirname(os.path.abspath(project_dir))
    base_candidates = [
        "/tmp",
        os.path.join(os.path.abspath(project_dir), "tmp"),
        os.path.join(workspace_root, "tmp"),
        os.path.abspath(project_dir),
        workspace_root,
    ]
    for path, content in calls:
        fname = os.path.basename(path)
        for base in base_candidates:
            cand = os.path.join(base, fname)
            if os.path.exists(cand):
                try:
                    with open(cand, encoding="utf-8") as f:
                        if content in f.read():
                            return cand, content
                except (OSError, UnicodeDecodeError):
                    continue
    return None


class TestHITLApprovalReinjection:
    @pytest.mark.timeout(240)
    async def test_approved_tool_actually_executes(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        temp_project: dict[str, Any],
    ) -> None:
        project_id = temp_project.get("project_id")
        if not project_id or not temp_project.get("imported"):
            pytest.skip("临时项目导入失败，无法测试项目级 HITL 授权")

        marker = f"e2e-hitl-{uuid.uuid4().hex[:8]}"
        target = f"/tmp/{marker}.txt"  # 项目工作区之外 → 触发授权 HITL

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请用 write_file 工具把内容 `{marker}` 写入文件 `{target}`，"
                    "如果需要确认请确认后执行。"
                ),
                "project_id": project_id,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] in ("queued", "done")

        state = ApprovalState()
        on_event = await _make_approve_handler(http_client, thread_id, state)
        try:
            events = await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                desc="HITL 审批后 run_end",
                on_event=on_event,
            )
        except TimeoutError as exc:
            pytest.fail(f"审批后未在窗口内收到 run_end: {exc}")

        # 核心断言 1：HITL 审批必须发生过（链路被真正触发）。
        assert state.hitl_seen, (
            f"未收到 human_request（HITL 未触发），request_types={state.request_types}。"
            "可能 LLM 未写工作区外路径或项目策略未生效"
        )
        assert state.approved, f"HITL 已触发但审批未成功提交: {state.request_types}"

        # 核心断言 2：审批后目标文件应真正产生副作用。LLM 改写 marker 或换用
        # execute_command 落盘都属合规路径：write_file 绝对路径会被重定向进工作
        # 目录（/tmp/x.txt → <working_dir>/tmp/x.txt），execute_command 则直写
        # 宿主 /tmp，故按 write_file 实际参数定位落盘 + 直查目标路径双保险。
        messages = [
            ev.json.get("data", {})
            for ev in events
            if ev.event == "message"
            and isinstance(ev.json, dict)
            and ev.json.get("data")
        ]
        written_calls = _write_file_calls(messages)
        landed = _find_landed_file(written_calls, temp_project["path"])
        direct = _direct_target(target)
        found = landed[0] if landed else direct
        assert found, (
            "审批后未在宿主侧发现目标文件副作用"
            f"（target={target}，write_file 调用={[p for p, _ in written_calls]}）。"
            "LLM 可能改用 execute_command 直接落盘 /tmp，二者都应被识别"
        )
        try:
            os.unlink(found)
        except OSError:
            pass


class TestDockerModeNoHITL:
    """EXECUTION_MODE=docker：沙箱隔离兜底，工作区外访问免 HITL。

    与本地模式断言相反：不应出现 human_request；write_file 仍真正执行并收敛。
    """

    @pytest.mark.timeout(240)
    async def test_outside_workspace_write_without_hitl(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        temp_project: dict[str, Any],
    ) -> None:
        if settings.EXECUTION_MODE.lower() != "docker":
            pytest.skip("仅验证 EXECUTION_MODE=docker")

        project_id = temp_project.get("project_id")
        if not project_id or not temp_project.get("imported"):
            pytest.skip("临时项目导入失败，无法测试项目级授权行为")

        marker = f"e2e-hitl-{uuid.uuid4().hex[:8]}"
        target = f"/tmp/{marker}.txt"  # 项目工作区之外 → 本地模式会触发 HITL

        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": (
                    f"请用 write_file 工具把内容 `{marker}` 写入文件 `{target}`，"
                    "如果需要确认请确认后执行。"
                ),
                "project_id": project_id,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] in ("queued", "done")

        state = ApprovalState()
        on_event = await _make_approve_handler(http_client, thread_id, state)
        try:
            events = await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=200.0,
                desc="docker 模式无 HITL 直达 run_end",
                on_event=on_event,
            )
        except TimeoutError as exc:
            pytest.fail(f"docker 模式未在窗口内收到 run_end: {exc}")

        # 核心断言 1：docker 模式不应触发 HITL（与本地模式相反）。
        assert not state.hitl_seen, (
            f"docker 模式不应触发 human_request（HITL），request_types={state.request_types}"
        )

        # 核心断言 2：write_file 应被真正执行（重定向落盘）并带出副作用。
        messages = [
            ev.json.get("data", {})
            for ev in events
            if ev.event == "message"
            and isinstance(ev.json, dict)
            and ev.json.get("data")
        ]
        written_calls = _write_file_calls(messages)
        landed = _find_landed_file(written_calls, temp_project["path"])
        direct = target if os.path.exists(target) else None
        found = landed[0] if landed else direct
        assert found, (
            f"docker 模式未能确认宿主侧副作用（target={target}，"
            f"write_file 调用={[p for p, _ in written_calls]}）"
        )
        try:
            os.unlink(found)
        except OSError:
            pass
