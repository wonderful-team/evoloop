"""真实移动端 / EvoCloud 网关链路 E2E 测试。

覆盖：
- 后端 EvoCloud 链接状态探测（/utils/evoloop-status、/devices/debug/status）
- 通过 `POST /api/v1/devices/{device_key}/command` 向本机后端发送各类远程指令，
  由 Gateway 转换为 command.relay 回送到后端，触发 EngineCommandSubscriber 处理
- 参数化 command_type：chat、stop、hitl_response、hitl_cancel、memory_add、
  conversation_update、conversation_delete

若后端未连接 Gateway、缺少 mobile 权益或 Gateway 不可达，
测试将失败并自动生成缺陷文档。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    collect_sse_until,
    gen_thread_id,
    observe_agent_run,
    verify_quota_exhausted_feedback,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _get_device_key(http_client: httpx.AsyncClient) -> str:
    """从后端状态接口获取本机 device_key。"""
    resp = await http_client.get("/api/v1/utils/evoloop-status")
    resp.raise_for_status()
    data = resp.json()
    device_key = data.get("device_key")
    if not device_key:
        pytest.fail(f"后端未注册 device_key，无法进行网关链路测试: {data}")
    return str(device_key)


async def _send_remote_command(
    http_client: httpx.AsyncClient,
    device_key: str,
    command_type: str,
    thread_id: str,
    params: dict[str, Any] | None = None,
    project_id: int = 0,
) -> dict[str, Any]:
    """通过后端设备命令接口发送真实 Gateway 命令。"""
    payload: dict[str, Any] = {
        "command_type": command_type,
        "thread_id": thread_id,
        "project_id": project_id,
    }
    if params is not None:
        payload["params"] = params

    resp = await http_client.post(
        f"/api/v1/devices/{device_key}/command",
        json=payload,
    )
    logger.info(
        "remote command %s thread=%s status=%s body=%s",
        command_type,
        thread_id,
        resp.status_code,
        resp.text[:200],
    )
    return {
        "status_code": resp.status_code,
        "text": resp.text[:500],
        "json": resp.json() if resp.status_code == 200 else None,
    }


class TestRealMobileGatewayLink:
    """真实移动端/网关链路。"""

    @pytest.mark.timeout(30)
    async def test_evoloop_status_and_link_state(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """EvoCloud 链接状态应可查询且返回真实状态。"""
        resp = await http_client.get("/api/v1/utils/evoloop-status")
        assert resp.status_code == 200, f"状态接口失败: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "connected" in data, f"状态接口缺少 connected 字段: {data}"
        assert "device_key" in data, f"状态接口缺少 device_key 字段: {data}"

        # 同时检查 debug 状态
        resp2 = await http_client.get("/api/v1/devices/debug/status")
        assert resp2.status_code == 200, f"debug 状态接口失败: {resp2.status_code}"
        debug = resp2.json()
        assert debug.get("is_connected") == data.get("connected"), (
            f"两个状态接口连接状态不一致: {data} vs {debug}"
        )

    @pytest.mark.timeout(120)
    @pytest.mark.parametrize(
        "command_type, params, expect_sse_run",
        [
            pytest.param(
                "chat",
                {"text": "你好，这是通过 Gateway command.relay 发送的真实消息。"},
                True,
                id="chat",
            ),
            pytest.param(
                "stop",
                {},
                False,
                id="stop",
            ),
            pytest.param(
                "hitl_response",
                {"response": "APPROVED"},
                False,
                id="hitl_response",
            ),
            pytest.param(
                "hitl_cancel",
                {},
                False,
                id="hitl_cancel",
            ),
            pytest.param(
                "memory_add",
                {
                    "name": f"e2e-real-gateway-{uuid.uuid4().hex[:8]}",
                    "description": "e2e-real-value",
                },
                False,
                id="memory_add",
            ),
            pytest.param(
                "conversation_update",
                {"title": "e2e-real-updated-title"},
                False,
                id="conversation_update",
            ),
            pytest.param(
                "conversation_delete",
                {},
                False,
                id="conversation_delete",
            ),
        ],
    )
    async def test_remote_command_relay_round_trip(
        self,
        http_client: httpx.AsyncClient,
        command_type: str,
        params: dict[str, Any],
        expect_sse_run: bool,
    ) -> None:
        """各类远程指令经 Gateway 回环到后端并被处理。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()

        result = await _send_remote_command(
            http_client, device_key, command_type, thread_id, params
        )

        if result["status_code"] == 403:
            pytest.fail(
                f"缺少 mobile 权益，无法测试远程指令: {result['text']}"
            )

        assert result["status_code"] == 200, (
            f"远程指令 {command_type} 发送失败: {result['status_code']} {result['text']}"
        )
        resp_data = result.get("json") or {}
        # Gateway 通常返回 {code, message, data}; code 0 表示已接受投递
        if "code" in resp_data:
            assert resp_data.get("code") == 0, (
                f"Gateway 返回业务错误: {resp_data}"
            )

        if expect_sse_run and command_type == "chat":
            # 验证后端确实把 command.relay/chat 当作用户消息启动 Agent
            events = await collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event == "run_end",
                timeout=120.0,
                desc=f"gateway chat run_end for {thread_id}",
            )
            run_end = next((ev.json for ev in events if ev.event == "run_end"), {})
            status = run_end.get("status")
            if status == "quota_exhausted":
                verify_quota_exhausted_feedback(events)
                return
            assert status in (
                "done",
                "failed",
                "quota_exhausted",
                "cancelled",
            ), f"Gateway chat 链路 run_end 终态异常: {run_end}"
            if status != "done":
                pytest.fail(
                    f"Gateway chat 经真实 LLM 后未正常完成，status={status}, run_end={run_end}"
                )

    @pytest.mark.timeout(60)
    async def test_remote_stop_cancels_running_chat(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """先通过 Gateway 发送 chat 启动运行，再发送 stop 应能终止。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()

        # 1. 发送 chat 指令启动运行（不等待完成，立即发 stop）
        await _send_remote_command(
            http_client,
            device_key,
            "chat",
            thread_id,
            {"text": "请写一个长一点的自我介绍，不要结束。"},
        )

        # 2. 等待 run_start 出现即发送 stop
        events = await collect_sse_until(
            http_client,
            f"/api/v1/stream/chat/{thread_id}",
            lambda ev: ev.event == "run_start",
            timeout=60.0,
            desc="wait for run_start before sending stop",
        )
        assert events, "未收到 run_start，无法验证 stop 命令"

        # 3. 发送 stop 远程指令
        stop_result = await _send_remote_command(
            http_client, device_key, "stop", thread_id
        )
        assert stop_result["status_code"] == 200, (
            f"stop 指令发送失败: {stop_result}"
        )

        # 4. 等待 run_end 并确认终态不是 running
        final_events = await collect_sse_until(
            http_client,
            f"/api/v1/stream/chat/{thread_id}",
            lambda ev: ev.event == "run_end",
            timeout=60.0,
            desc="run_end after stop command",
        )
        run_end = next(
            (ev.json for ev in final_events if ev.event == "run_end"), {}
        )
        status = run_end.get("status")
        if status == "quota_exhausted":
            verify_quota_exhausted_feedback(final_events)
            return
        assert status in (
            "done",
            "failed",
            "cancelled",
        ), f"stop 后 run_end 终态异常: {run_end}"


class TestRemoteCommandLifecycle:
    """真实移动端/网关完整生命周期指令。"""

    @pytest.mark.timeout(120)
    async def test_remote_memory_lifecycle_commands_accepted(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """memory_add/update/delete 三类指令经 Gateway 投递均被接受，且 update/delete
        作用于同一条记忆（同一 name），而非 no-op 的随机名。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()
        mem_name = f"e2e-gateway-mem-{uuid.uuid4().hex[:6]}"

        for command_type, params in (
            (
                "memory_add",
                {
                    "name": mem_name,
                    "description": "initial",
                    "project_id": 0,
                },
            ),
            (
                "memory_update",
                {
                    "name": mem_name,
                    "description": "updated",
                    "project_id": 0,
                },
            ),
            (
                "memory_delete",
                {"name": mem_name, "project_id": 0},
            ),
        ):
            result = await _send_remote_command(
                http_client, device_key, command_type, thread_id, params
            )
            assert result["status_code"] == 200, (
                f"{command_type} 指令投递失败: {result['status_code']} {result['text']}"
            )
            # 修复后 devices.send_command 返回 gateway handleCommandRelay 的
            # data 子对象（{command_id, message_id, thread_id}），不再透传顶层
            # code 字段。code==0 的语义由 HTTP 200 覆盖，这里验证成功接受：
            # 返回了 command_id 即表示 gateway 已创建命令并回送。
            if result["json"] is not None:
                assert result["json"].get("command_id") is not None, (
                    f"Gateway 业务错误 ({command_type}): {result['json']}"
                )

    @pytest.mark.timeout(120)
    async def test_remote_retry_on_existing_thread(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """先通过 chat 端点创建真实对话，再经 Gateway 发送 retry 指令。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()

        # 创建一条真实用户消息并等待首次运行结束（终态可能为失败，不影响 retry 测试）
        observer = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=60.0, expect_start=False)
        )
        await asyncio.sleep(0)
        chat_resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "Gateway retry 测试消息", "project_id": 0},
        )
        assert chat_resp.status_code == 200, chat_resp.text
        await observer

        result = await _send_remote_command(
            http_client, device_key, "retry", thread_id, params={}
        )
        assert result["status_code"] == 200, (
            f"retry 指令投递失败: {result['status_code']} {result['text']}"
        )
        if result["json"] is not None:
            assert result["json"].get("command_id") is not None, (
                f"Gateway 业务错误: {result['json']}"
            )

    @pytest.mark.timeout(120)
    async def test_remote_rewind_on_existing_thread(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """先通过 chat 端点创建真实对话，再经 Gateway 发送 rewind 指令。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()

        observer = asyncio.create_task(
            observe_agent_run(http_client, thread_id, timeout=60.0, expect_start=False)
        )
        await asyncio.sleep(0)
        chat_resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "Gateway rewind 测试消息", "project_id": 0},
        )
        assert chat_resp.status_code == 200, chat_resp.text
        await observer

        result = await _send_remote_command(
            http_client, device_key, "rewind", thread_id, params={}
        )
        assert result["status_code"] == 200, (
            f"rewind 指令投递失败: {result['status_code']} {result['text']}"
        )
        if result["json"] is not None:
            assert result["json"].get("command_id") is not None, (
                f"Gateway 业务错误: {result['json']}"
            )


class TestRemoteCommandEdgeCases:
    """真实移动端/网关指令边界场景。"""

    @pytest.mark.timeout(30)
    async def test_invalid_command_type(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """非法 command_type 不应 500，应明确拒绝或返回业务错误。"""
        device_key = await _get_device_key(http_client)
        thread_id = gen_thread_id()
        result = await _send_remote_command(
            http_client, device_key, "not_a_real_command", thread_id
        )
        assert result["status_code"] in (200, 400, 422), (
            f"非法 command_type 不应导致服务端错误: {result['status_code']} {result['text']}"
        )
        if result["status_code"] == 200:
            body = result.get("json") or {}
            assert body.get("code") != 0 or "not" in body.get("message", "").lower(), (
                f"非法 command_type 应返回业务错误: {body}"
            )

    @pytest.mark.timeout(30)
    async def test_nonexistent_device_key(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """不存在的 device_key 应返回 404 或 400，不应 500。"""
        thread_id = gen_thread_id()
        resp = await http_client.post(
            "/api/v1/devices/fake-device-key-not-exist/command",
            json={
                "command_type": "chat",
                "thread_id": thread_id,
                "project_id": 0,
                "params": {"text": "test"},
            },
        )
        assert resp.status_code in (404, 400), (
            f"不存在 device_key 不应 500: {resp.status_code} {resp.text[:200]}"
        )
