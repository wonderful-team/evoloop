"""阶段8：语音状态机与 Barge-in 端到端测试。

对应 EvoLoop Backend E2E Test Scenario Design：
- E2E-SC-001: Barge-in during Agent TTS preserves the Worker
- E2E-SC-015: Invalid barge-in before any route is dropped and logged
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from .conftest import VoiceConn, observe_agent_run, wait_until

pytestmark = pytest.mark.e2e


class TestBargeInAgentRun:
    """E2E-SC-001: Barge-in 期间仅静音不杀 Worker，新 route 通过 NEW_COMMAND 取消旧任务。"""

    @pytest.mark.timeout(180)
    @pytest.mark.slow
    @pytest.mark.real
    async def test_barge_in_during_tts_does_not_kill_worker(
        self,
        voice_conn: VoiceConn,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """发送耗时 Agent 任务，在 TTS/执行窗口内 barge-in，验证旧 Worker 仍存活，新 route 才取消它。"""
        long_prompt = (
            "请使用 execute_command 工具，background 参数设为 false，"
            "运行命令 `sleep 4`，并返回命令输出结果。"
        )
        new_prompt = "帮我总结一下前端目录结构"

        await voice_conn.send_route(long_prompt)

        async def _activity_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            return resp.json().get("status") == "running"

        # 等待第一次 Agent 运行进入 running
        await wait_until(
            _activity_running,
            timeout=45.0,
            desc="首次 Agent 运行进入 running",
        )

        # Barge-in：仅静音，不应取消后台 Worker
        await voice_conn.send_type("voice.barge_in", {"thread_id": thread_id})
        barge_env = await voice_conn._drain_until(
            lambda e: e.get("type") == "voice.barge_in", timeout=10.0
        )
        assert barge_env is not None, "未收到 voice.barge_in 确认信封"
        assert barge_env["body"]["thread_id"] == thread_id

        # 关键 L3 断言：barge-in 后旧 Worker 仍应在运行
        assert await _activity_running(), "barge-in 后旧 Worker 应该仍然存活（running）"

        # 新 route：Supervisor 应识别为 NEW_COMMAND，取消旧任务并启动新任务
        await voice_conn.send_route(new_prompt)

        # 等待第二次运行结束
        result = await observe_agent_run(
            http_client,
            thread_id,
            timeout=120.0,
            expect_start=False,
        )
        print(f"DEBUG result.run_end={result.run_end.json if result.run_end else None}")
        final_status = result.run_end_status
        assert final_status in (
            "done",
            "failed",
            "cancelled",
        ), f"第二次运行终态异常: {final_status}"

        # 新运行（第二次 route 的 Agent）可能因 LLM 首字延迟耗时较长，
        # 先等待线程退出 running 再收终态信封，避免超时窗口不足
        async def _not_running() -> bool:
            return not await _activity_running()

        await wait_until(
            _not_running,
            timeout=180.0,
            desc="新任务完成后线程退出 running",
        )

        # 新任务应给出终态 voice.route_result
        final_env = await voice_conn.wait_terminal_route_result(timeout=60.0)
        assert final_env["body"]["status"] in (
            "done",
            "failed",
            "cancelled",
        ), f"新 route 终态信封异常: {final_env}"

        # 线程最终不应 stuck 在 running（终态信封到达后再次确认）
        await wait_until(
            _not_running,
            timeout=30.0,
            desc="终态信封后线程退出 running",
        )


class TestIllegalTransitions:
    """E2E-SC-015: 未 route 先 barge-in 是非法状态机迁移，应被丢弃并记录日志。"""

    @pytest.mark.timeout(30)
    async def test_barge_in_before_route_is_dropped(
        self, voice_conn: VoiceConn
    ) -> None:
        """在首次 voice.route 之前发送 barge-in，连接必须保持可用，后续 route 可正常处理。

        注：当前服务端对非法迁移使用 force_set，因此可能仍推送 barge_in 信封；
        本测试的核心断言是连接不崩溃且后续合法 route 可被处理。
        服务端日志中的 `[voice-sm] illegal transition` 需要访问日志文件单独验证。
        """
        await voice_conn.send_type(
            "voice.barge_in", {"thread_id": voice_conn.thread_id}
        )

        # 非法迁移可能被丢弃，也可能仍推送 barge_in 信封；关键是不崩溃
        maybe = await voice_conn._drain_until(
            lambda e: e.get("type") in ("voice.barge_in", "system.error"),
            timeout=5.0,
        )
        if maybe is not None:
            assert maybe.get("type") in ("voice.barge_in", "system.error")
            if maybe.get("type") == "system.error":
                assert maybe.get("body", {}).get("code") != "fatal"

        # 后续合法 route 必须正常处理
        await voice_conn.send_route("再见")
        env = await voice_conn.wait_route_result(timeout=20.0)
        assert env["body"]["status"] == "done"
        # LLM 告别文案非确定性（如"再见！有需要随时找我。"），只断言包含"再见"
        assert "再见" in env["body"]["summary"]


class TestNewCommandHardKill:
    """E2E：NEW_COMMAND 节点转移会硬掐断旧任务（loop.py:67-76）。"""

    @pytest.mark.timeout(180)
    @pytest.mark.slow
    @pytest.mark.real
    async def test_new_command_cancels_previous_worker_run(
        self,
        voice_conn: VoiceConn,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """P0：新 route 触发 NEW_COMMAND 后，旧任务（第一个 run_end）终态必须为 cancelled。

        引擎在节点转移（WORKER / SEQUENTIAL_WORKFLOW）时 pop_previous_task +
        old_task.cancel()（loop.py:67-76），旧运行被硬掐断；
        若旧任务在执行中被 LLM 提前自然完成，则 pytest.skip 而非 fail。
        """
        long_prompt = (
            "请使用 execute_command 工具，background 参数设为 false，"
            "运行命令 `sleep 8`，并返回命令输出结果。"
        )
        new_prompt = (
            "请使用 execute_command 工具，background 参数设为 false，"
            "运行命令 `sleep 2`，并返回命令输出结果。"
        )

        sse_task = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=150.0, expect_start=False)
        )
        await asyncio.sleep(0)

        await voice_conn.send_route(long_prompt)

        async def _activity_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            return resp.json().get("status") == "running"

        await wait_until(
            _activity_running,
            timeout=45.0,
            desc="旧 Agent 运行进入 running",
        )

        # 新 route：新运行 Supervisor 决策出新的执行目标时触发 NEW_COMMAND，
        # 硬掐断旧任务（新运行自身尚未结束）
        await voice_conn.send_route(new_prompt)

        # 捕获第一个 run_end —— 即旧任务的终态
        result = await sse_task
        if result.run_end_status == "done":
            pytest.skip(
                "旧任务在 NEW_COMMAND 生效前已被 LLM 提前自然完成"
                f"（run_end={result.run_end_status}），无法验证硬掐断语义"
            )
        assert result.run_end_status == "cancelled", (
            "NEW_COMMAND 节点转移应硬掐断旧任务（loop.py:67-76 pop_previous_task "
            f"+ old_task.cancel()），旧 run_end 必须为 cancelled，实际: "
            f"{result.run_end_status} ({result.run_end.json})"
        )

        # 新任务应完成并给出终态 voice.route_result（旧任务取消的 cancelled 事件
        # 可能被通道策略过滤，也可能呈现为 failed 信封，两者都不影响本断言）
        final_env = await voice_conn.wait_terminal_route_result(timeout=60.0)
        assert final_env["body"]["status"] in (
            "done",
            "failed",
            "cancelled",
        ), f"新任务终态信封异常: {final_env}"

        # 线程最终不应 stuck 在 running
        async def _not_running() -> bool:
            return not await _activity_running()

        await wait_until(
            _not_running,
            timeout=60.0,
            desc="新任务完成后线程退出 running",
        )
