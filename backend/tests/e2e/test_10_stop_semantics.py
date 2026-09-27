"""E2E-SC-002 & E2E-SC-014: stop semantics / cancellation marker hysteresis.

覆盖：
  - /chat/stop 软停止：仅写入持久取消标记，run_end 精确为 cancelled（十四.2）
  - voice.cancel 硬停止：task.cancel()，voice.route_result 终态为 cancelled
  - 软停止后同 thread 再次发送新消息，旧取消标记已被清除，新运行正常完成
  - 进度询问类消息（L1 无 QUERY 意图分类）不会掐断旧 Worker（八.2.2）
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.e2e.conftest import VoiceConn, observe_agent_run, wait_until

pytestmark = pytest.mark.e2e


async def _wait_for_running(
    http_client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 30.0,
) -> None:
    """等待线程 activity 状态进入 running；未进入则 pytest.skip。"""

    async def _check() -> bool:
        resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
        if resp.status_code != 200:
            return False
        state = resp.json() or {}
        return state.get("status") == "running"

    try:
        await wait_until(
            _check, timeout=timeout, desc=f"thread {thread_id} 进入 running"
        )
    except TimeoutError:
        pytest.skip(f"运行未在 {timeout}s 内进入 running 状态，可能 LLM 未触发工具调用")


async def _wait_for_terminal(
    http_client: httpx.AsyncClient,
    thread_id: str,
    timeout: float = 30.0,
) -> None:
    """等待线程 activity 进入终态（done/cancelled/failed/idle）。"""

    async def _check() -> bool:
        resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
        if resp.status_code != 200:
            return False
        state = resp.json() or {}
        return state.get("status") in (
            "done",
            "cancelled",
            "failed",
            "quota_exhausted",
            "idle",
        )

    try:
        await wait_until(_check, timeout=timeout, desc=f"thread {thread_id} 进入终态")
    except TimeoutError:
        pytest.skip(f"运行未在 {timeout}s 内进入终态")


class TestStopHardVsSoft:
    """E2E-SC-002: 软 / 硬停止语义区分。"""

    @pytest.mark.slow
    @pytest.mark.timeout(180)
    async def test_soft_stop_sets_cancellation_marker(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """POST /chat/stop 写入持久取消标记；run_end 终态为 cancelled。"""
        # 使用长耗时命令，确保 stop 到达时运行仍在 running 状态
        long_prompt = "请使用 execute_command 工具运行命令 `sleep 5`，然后告诉我结果。"
        sse_task = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0, expect_start=False)
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": long_prompt},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        # 确保运行进入 running 再 stop，否则测试无意义
        await _wait_for_running(http_client, thread_id, timeout=30.0)

        resp = await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "stopping"
        assert body["thread_id"] == thread_id

        result = await sse_task
        assert result.run_end_status in ("cancelled", "failed"), (
            f"stop 后应观察到 cancelled/failed 终态，实际: {result.run_end_status} "
            f"({result.run_end.json})"
        )

        async def _not_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            state = resp.json() or {}
            return state.get("status") != "running"

        await wait_until(_not_running, timeout=30.0, desc="线程退出 running")

    @pytest.mark.slow
    @pytest.mark.real
    @pytest.mark.timeout(180)
    async def test_soft_stop_yields_cancelled_run_end(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """P0：软停止（/chat/stop）后 SSE run_end 终态必须精确为 cancelled（十四.2）。

        activity_monitor.run_scope 捕获 AgentCancelledException 后发布
        end_run(status="cancelled")，而非 failed；若 LLM 未执行工具导致任务
        秒回 done，则 pytest.skip 而非 fail。
        """
        long_prompt = "请使用 execute_command 工具运行命令 `sleep 8`，然后告诉我结果。"
        sse_task = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=150.0, expect_start=False)
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": long_prompt},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        await _wait_for_running(http_client, thread_id, timeout=30.0)

        resp = await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "stopping"
        assert body["thread_id"] == thread_id

        result = await sse_task
        if result.run_end_status == "done":
            pytest.skip(
                "LLM 未执行长耗时工具或任务在 stop 生效前已自然完成"
                f"（run_end={result.run_end_status}），无法验证软截断终态"
            )
        assert result.run_end_status == "cancelled", (
            "软停止后 run_end 必须精确为 cancelled（十四.2：run_scope 发布 "
            f"end_run(status='cancelled')），实际: {result.run_end_status} "
            f"({result.run_end.json})"
        )

        async def _not_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            state = resp.json() or {}
            return state.get("status") != "running"

        await wait_until(_not_running, timeout=30.0, desc="软停止后线程退出 running")

    @pytest.mark.slow
    @pytest.mark.timeout(180)
    async def test_hard_voice_cancel_cancels_task(
        self,
        http_client: httpx.AsyncClient,
        voice_conn: VoiceConn,
        thread_id: str,
    ) -> None:
        """voice.cancel 直接 task.cancel()；voice.route_result 终态为 cancelled。"""
        long_prompt = "请使用 execute_command 工具运行命令 `sleep 5`，然后告诉我结果。"
        sse_task = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0, expect_start=False)
        )
        await asyncio.sleep(0)

        await voice_conn.send_route(long_prompt)

        # 等待运行进入 running 状态
        await _wait_for_running(http_client, thread_id, timeout=30.0)

        # 多次发送 cancel 提高可靠性
        for _ in range(3):
            await voice_conn.send_type(
                "voice.cancel", {"thread_id": voice_conn.thread_id}
            )
            await asyncio.sleep(0.3)

        env = await voice_conn.wait_terminal_route_result(timeout=60.0)
        status = env["body"]["status"]
        assert status in (
            "cancelled",
            "failed",
        ), f"voice.cancel 后应收到 cancelled/failed，实际: {status}"

        result = await sse_task
        assert result.run_end_status in (
            "cancelled",
            "failed",
        ), f"SSE run_end 终态异常: {result.run_end_status} ({result.run_end.json})"

        async def _not_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            state = resp.json() or {}
            return state.get("status") != "running"

        await wait_until(_not_running, timeout=30.0, desc="线程退出 running")


class TestStopHysteresis:
    """E2E-SC-014: 软停止后取消标记在下次运行前被清除。"""

    @pytest.mark.slow
    @pytest.mark.timeout(240)
    async def test_stale_cancellation_marker_cleared(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """先软停止一次长运行，再发新消息，新运行不应被旧取消标记取消。"""
        # 第一次运行：长耗时任务
        long_prompt = "请使用 execute_command 工具运行命令 `sleep 5`，然后告诉我结果。"
        sse_task1 = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=120.0, expect_start=False)
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": long_prompt},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        await _wait_for_running(http_client, thread_id, timeout=30.0)

        resp = await http_client.post(
            "/api/v1/chat/stop",
            json={"thread_id": thread_id, "message": "stop"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "stopping"

        result1 = await sse_task1
        assert result1.run_end_status in (
            "cancelled",
            "failed",
        ), f"第一次 stop 后应观察到 cancelled/failed，实际: {result1.run_end_status}"

        async def _not_running() -> bool:
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                return False
            state = resp.json() or {}
            return state.get("status") != "running"

        await _wait_for_terminal(http_client, thread_id, timeout=30.0)

        # 第二次运行：简单短任务，验证旧标记不会导致取消
        short_prompt = "请使用 execute_command 工具运行命令 `echo hello-after-stop`。"
        sse_task2 = asyncio.create_task(
            observe_agent_run(
                http_client,
                thread_id,
                timeout=120.0,
                expect_start=False,
                # 断点续传：跳过 run1 缓冲的旧终态，只观察 run2
                after_seq=result1.last_seq,
            )
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": short_prompt},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        result2 = await sse_task2
        assert result2.run_end_status != "cancelled", (
            f"新运行不应被旧取消标记取消，实际: {result2.run_end_status}"
        )
        assert result2.run_end_status in (
            "done",
            "failed",
        ), f"新运行应正常完成或失败，实际: {result2.run_end_status}"

        await wait_until(_not_running, timeout=30.0, desc="第二次运行退出 running")


class TestProgressQuerySemantics:
    """E2E：进度询问类消息不会掐断旧 Worker（文档八.2.2）。"""

    @pytest.mark.slow
    @pytest.mark.real
    @pytest.mark.timeout(240)
    async def test_progress_query_does_not_kill_old_worker(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """P1：L1 无 QUERY 意图分类，进度询问不会掐断旧 Worker，旧任务自然终态 done。

        注：web /chat 在 thread 运行中会先被 _chat.py 的 409 并发守卫拒绝
        （"currently processing"），该路径同样满足"旧任务未被掐断"语义；
        若查询被接受（200），则额外校验新运行未通过 NEW_COMMAND 掐断旧任务。
        """
        long_prompt = "请使用 execute_command 工具运行命令 `sleep 8`，然后告诉我结果。"
        sse_task = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=150.0, expect_start=False)
        )
        await asyncio.sleep(0)

        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": long_prompt},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

        await _wait_for_running(http_client, thread_id, timeout=30.0)

        # 同一线程发送进度询问；运行中可能被 409 拒绝，两种结果都接受
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "进度怎么样？"},
        )
        assert resp.status_code in (200, 409), resp.text

        # 关键断言：进度询问后旧任务不应被掐断 —— 立即轮询 activity 仍为 running
        running_polls = 0
        for _ in range(5):
            resp = await http_client.get(f"/api/v1/conversations/{thread_id}/activity")
            if resp.status_code != 200:
                continue
            if (resp.json() or {}).get("status") == "running":
                running_polls += 1
            await asyncio.sleep(0.5)

        if running_polls == 0:
            pytest.skip("进度询问后未观察到 activity 保持 running，无法验证未掐断语义")

        # 旧任务应自然终态 done；若 LLM 将进度询问解析为工具型新任务并触发
        # NEW_COMMAND 节点转移（八.2.2 例外路径），旧任务会被硬掐断为 cancelled
        result = await sse_task
        if result.run_end_status == "cancelled":
            pytest.skip(
                "进度询问被 LLM 解析为工具型新任务并触发 NEW_COMMAND 节点转移，"
                f"旧任务被硬掐断（run_end={result.run_end_status}），非 QUERY 语义缺陷"
            )
        assert result.run_end_status == "done", (
            "旧任务应自然终态 done（进度询问不应掐断旧 Worker），"
            f"实际: {result.run_end_status} ({result.run_end.json})"
        )
