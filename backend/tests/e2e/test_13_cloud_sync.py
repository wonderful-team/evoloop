"""阶段：云同步端到端测试。

覆盖：
  - E2E-SC-005：会话重命名触发增量同步（pending → synced）
  - E2E-SC-013：rewind 触发 EvoCloud 批量消息清理（MESSAGES_CLEANUP）

注意：本模块依赖真实的 EvoCloud Gateway 链路（MOBILE_SYNC_ENABLED）。
当真实网关不可达时，使用 respx 模拟网关响应，以验证本地同步事件与
 outbound HTTP 调用。SQLite 直接查询仅用于读取 sync_status（服务端未暴露
该字段）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    AgentLoopResult,
    collect_sse_until,
    observe_agent_run,
    wait_until,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# 本地 SQLite 辅助（仅读取，不修改）
# ---------------------------------------------------------------------------


async def _get_db_path(http_client: httpx.AsyncClient) -> Path:
    """从 /api/v1/system/config 解析 SQLite 数据库路径。"""
    resp = await http_client.get("/api/v1/system/config")
    resp.raise_for_status()
    configs = {
        item.get("key"): item.get("value")
        for item in resp.json()
        if isinstance(item, dict)
    }

    sqlite_path = configs.get("SQLITE_PATH")
    if sqlite_path:
        return Path(os.path.expanduser(sqlite_path)).expanduser()

    app_data_dir = configs.get("EVOLOOP_APP_DATA_DIR")
    if app_data_dir:
        base = Path(os.path.expanduser(app_data_dir)).expanduser()
    else:
        base = Path.home() / ".evoloop"
    return base / "database" / "backend.db"


async def _query_db(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """在线程中执行 SQLite 查询，避免在 async 函数中直接阻塞。"""

    def _run() -> list[Any]:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return list(cur.fetchall())
        finally:
            conn.close()

    return await asyncio.to_thread(_run)


async def _conversation_sync_status(
    _http_client: httpx.AsyncClient, db_path: Path, thread_id: str
) -> str | None:
    """读取 conversations.sync_status。"""
    rows = await _query_db(
        db_path, "SELECT sync_status FROM conversations WHERE id = ?", (thread_id,)
    )
    return rows[0]["sync_status"] if rows else None


async def _mobile_sync_enabled(http_client: httpx.AsyncClient) -> bool:
    """探测系统配置中是否开启了移动端云同步。"""
    resp = await http_client.get("/api/v1/system/config")
    resp.raise_for_status()
    value = next(
        (
            item.get("value")
            for item in resp.json()
            if isinstance(item, dict) and item.get("key") == "MOBILE_SYNC_ENABLED"
        ),
        None,
    )
    return str(value).lower() in ("true", "1", "yes")


async def _probe_sync_interception(http_client: httpx.AsyncClient) -> None:
    """探测 respx 能否拦截后端出站云同步请求。

    外部 E2E 模式下后端是独立进程，respx 只能拦截测试进程内的 httpx 调用，
    无法拦截后端/Huey worker 的云同步请求 —— 此时跳过依赖请求断言的用例，
    避免 ``assert route.called`` 必然失败。
    """
    respx = pytest.importorskip("respx")
    status = await http_client.get("/api/v1/utils/evoloop-status")
    status.raise_for_status()
    device_key = status.json().get("device_key")
    if not device_key:
        pytest.skip("后端未注册 device_key，跳过云同步用例")
    with respx.mock:
        probe_route = respx.get(path="/evolooplink/api/log/recent").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": []})
        )
        try:
            await http_client.get(
                f"/api/v1/devices/{device_key}/logs", timeout=15.0
            )
        except Exception as exc:
            logger.debug("设备日志探测请求异常: %s", exc)
        if not probe_route.called:
            pytest.skip(
                "respx 无法拦截后端出站云同步请求（后端为独立进程），"
                "云同步请求断言用例仅在进程内运行模式下可用"
            )


# ---------------------------------------------------------------------------
# 同步测试
# ---------------------------------------------------------------------------


class TestConversationSync:
    """E2E-SC-005：会话重命名触发增量同步。"""

    @pytest.mark.real
    @pytest.mark.timeout(180)
    async def test_rename_triggers_incremental_sync(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """PATCH 重命名后，本地 sync_status 经 pending 最终变为 synced，且云端收到
        包含新标题的增量同步请求。"""
        respx = pytest.importorskip("respx")

        if not await _mobile_sync_enabled(http_client):
            pytest.skip("MOBILE_SYNC_ENABLED 未开启，跳过真实云同步测试")

        await _probe_sync_interception(http_client)

        db_path = await _get_db_path(http_client)
        new_title = f"E2E Sync Title {uuid.uuid4().hex[:8]}"

        # 使用 respx 模拟 EvoCloud Gateway 的同步端点，允许任务链成功。
        with respx.mock:
            sync_conv_route = respx.post(
                path="/evolooplink/api/sync/conversation"
            ).mock(return_value=httpx.Response(200, json={"code": 0, "data": {}}))
            respx.post(path="/evolooplink/api/sync/messages").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )

            # 订阅 SSE，在 run_start 后立刻 PATCH 重命名，确保重命名发生在首次同步
            # 完成之前，使本次 run_end 触发的增量同步携带新标题。
            renamed = False

            async def _on_event(ev) -> None:
                nonlocal renamed
                if ev.event == "run_start" and not renamed:
                    renamed = True
                    patch_resp = await http_client.patch(
                        f"/api/v1/conversations/{thread_id}",
                        json={"title": new_title},
                    )
                    assert patch_resp.status_code == 200, patch_resp.text
                    body = patch_resp.json()
                    assert body["status"] == "updated"
                    assert body["title"] == new_title

            sse_task = asyncio.create_task(
                collect_sse_until(
                    http_client,
                    f"/api/v1/stream/chat/{thread_id}",
                    lambda ev: ev.event == "run_end",
                    timeout=120.0,
                    desc="首次 Agent 运行结束",
                    on_event=_on_event,
                )
            )
            await asyncio.sleep(0)  # 确保 SSE 任务先建立连接

            chat_resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": "你好，请用一句话介绍自己"},
            )
            assert chat_resp.status_code == 200, chat_resp.text
            assert chat_resp.json()["status"] == "queued"

            await sse_task

        # 等待 Huey 任务将本地 sync_status 更新为 synced。
        async def _synced() -> bool:
            status = await _conversation_sync_status(http_client, db_path, thread_id)
            return status == "synced"

        try:
            await wait_until(_synced, timeout=60.0, desc="conversation sync_status 变为 synced")
        except TimeoutError as exc:
            raise AssertionError(
                f"会话 {thread_id} 重命名后 sync_status 未在 60s 内变为 synced，"
                f"当前状态: {await _conversation_sync_status(http_client, db_path, thread_id)}"
            ) from exc

        # 断言至少一次同步请求包含新标题和当前 thread_id。
        assert sync_conv_route.called, "未发起 conversation 增量同步请求"
        synced_titles = [
            json.loads(call.request.content).get("conversation", {}).get("title")
            for call in sync_conv_route.calls
        ]
        assert new_title in synced_titles, (
            f"云端同步请求未包含新标题 {new_title}，实际 titles={synced_titles}"
        )
        synced_ids = {
            json.loads(call.request.content).get("conversation", {}).get("id")
            for call in sync_conv_route.calls
        }
        assert thread_id in synced_ids, (
            f"云端同步请求未包含 thread_id={thread_id}，实际 ids={synced_ids}"
        )


class TestCloudSyncRewind:
    """E2E-SC-013：rewind 触发 EvoCloud MESSAGES_CLEANUP 批量删除。"""

    @pytest.mark.real
    @pytest.mark.timeout(180)
    async def test_rewind_sends_cloud_delete_batch(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """rewind 删除本地消息后，EvoCloud 同步子系统应发送包含目标序列的
        rewindMessages 请求。"""
        respx = pytest.importorskip("respx")

        if not await _mobile_sync_enabled(http_client):
            pytest.skip("MOBILE_SYNC_ENABLED 未开启，跳过真实云同步测试")

        await _probe_sync_interception(http_client)

        # 1. 运行一次会产生 AI 回复的对话，并记录 human 消息。
        chat_resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "你好，请用一句话回应"},
        )
        assert chat_resp.status_code == 200, chat_resp.text
        assert chat_resp.json()["status"] == "queued"

        result = await observe_agent_run(http_client, thread_id, timeout=120.0)
        assert result.run_end_status in ("done", "failed"), (
            f"运行未到达终态: {result.run_end_status}"
        )

        msgs_resp = await http_client.get(
            f"/api/v1/conversations/{thread_id}/messages"
        )
        msgs_resp.raise_for_status()
        messages = msgs_resp.json().get("data", [])
        human = next((m for m in messages if m.get("role") == "human"), None)
        assert human is not None, "消息历史中未找到 human 消息"
        human_id = human["id"]
        human_seq = human.get("sequence_number")

        removed_ids = {m["id"] for m in messages if m.get("id") != human_id}

        # 2. 模拟云端清理端点。
        with respx.mock:
            rewind_route = respx.post(
                path="/evolooplink/api/sync/rewindMessages"
            ).mock(return_value=httpx.Response(200, json={"code": 0, "data": {}}))
            # 兼容旧版 fallback（target_sequence=0 时走 deleteMessages）
            delete_route = respx.post(
                path="/evolooplink/api/sync/deleteMessages"
            ).mock(return_value=httpx.Response(200, json={"code": 0, "data": {}}))

            rewind_resp = await http_client.post(
                f"/api/v1/conversations/{thread_id}/rewind",
                json={"message_id": human_id, "revert_files": False},
            )
            assert rewind_resp.status_code == 200, rewind_resp.text
            body = rewind_resp.json()
            assert body["status"] == "rewound"
            assert body["removed_count"] >= len(removed_ids)

            # 等待 EvoCloudSyncCleanupSubscriber 发送云端清理请求。
            async def _rewind_synced() -> bool:
                return rewind_route.called or delete_route.called

            try:
                await wait_until(
                    _rewind_synced,
                    timeout=30.0,
                    desc="rewind 云端清理请求发出",
                )
            except TimeoutError as exc:
                raise AssertionError(
                    "rewind 后未在 30s 内观察到云端清理请求"
                ) from exc

        # 3. 断言本地消息已删除。
        after_resp = await http_client.get(
            f"/api/v1/conversations/{thread_id}/messages"
        )
        after_ids = {m["id"] for m in after_resp.json().get("data", [])}
        assert after_ids.isdisjoint(removed_ids), (
            f"rewind 后仍有消息未被删除: {after_ids & removed_ids}"
        )

        # 4. 断言云端清理请求参数。
        if rewind_route.called:
            request = rewind_route.calls.last.request
            payload = json.loads(request.content)
            assert payload.get("thread_id") == thread_id, (
                f"云端 rewind 请求 thread_id 不匹配: {payload.get('thread_id')}"
            )
            assert payload.get("include_target") is True, (
                f"云端 rewind 请求未包含 include_target=True: {payload}"
            )
            if human_seq is not None:
                assert payload.get("target_sequence") == human_seq, (
                    f"云端 rewind 请求 target_sequence 不匹配: "
                    f"期望 {human_seq}，实际 {payload.get('target_sequence')}"
                )
        else:
            request = delete_route.calls.last.request
            payload = json.loads(request.content)
            assert payload.get("thread_id") == thread_id
            deleted_ids = set(payload.get("message_ids", []))
            assert removed_ids.issubset(deleted_ids), (
                f"fallback delete 请求未包含所有被删除消息: {deleted_ids}"
            )


# ---------------------------------------------------------------------------
# 云同步失败 / 重试路径
# ---------------------------------------------------------------------------


async def _run_chat_and_wait_end(
    http_client: httpx.AsyncClient, thread_id: str, message: str
) -> AgentLoopResult:
    """发起一次 Agent 运行并等待 run_end（run_end 会触发增量同步）。"""
    chat_resp = await http_client.post(
        "/api/v1/chat",
        json={"thread_id": thread_id, "message": message},
    )
    assert chat_resp.status_code == 200, chat_resp.text
    assert chat_resp.json()["status"] == "queued"
    return await observe_agent_run(http_client, thread_id, timeout=120.0)


class TestConversationSyncFailureRetry:
    """E2E-SC-005b：云同步失败后重试恢复（pending 保持 → 恢复 200 → synced）。"""

    @pytest.mark.real
    @pytest.mark.timeout(240)
    async def test_sync_failure_keeps_pending_then_retry_syncs(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """respx 将云端同步接口 mock 成 500 时 sync_status 保持 pending；恢复 200 后
        再次触发同步最终变回 synced。"""
        respx = pytest.importorskip("respx")

        if not await _mobile_sync_enabled(http_client):
            pytest.skip("MOBILE_SYNC_ENABLED 未开启，跳过云同步失败/重试用例")

        # 探测 respx 是否能拦截后端出站请求（后端须与测试同进程运行）。
        status = await http_client.get("/api/v1/utils/evoloop-status")
        status.raise_for_status()
        device_key = status.json().get("device_key")
        if not device_key:
            pytest.skip("后端未注册 device_key，跳过云同步失败/重试用例")

        with respx.mock:
            probe_route = respx.get(path="/evolooplink/api/log/recent").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": []})
            )
            try:
                await http_client.get(
                    f"/api/v1/devices/{device_key}/logs", timeout=15.0
                )
            except Exception as exc:
                logger.debug("设备日志探测请求异常: %s", exc)
            if not probe_route.called:
                pytest.skip(
                    "respx 无法拦截后端出站云同步请求（后端为独立进程），"
                    "云同步失败/重试用例仅在进程内运行模式下可用"
                )

        db_path = await _get_db_path(http_client)

        # ---- 阶段 1：mock 500，同步应失败且 sync_status 保持 pending ----
        with respx.mock:
            conv_500 = respx.post(path="/evolooplink/api/sync/conversation").mock(
                return_value=httpx.Response(
                    500, json={"code": -1, "message": "mock 500"}
                )
            )
            msg_500 = respx.post(path="/evolooplink/api/sync/messages").mock(
                return_value=httpx.Response(
                    500, json={"code": -1, "message": "mock 500"}
                )
            )

            result = await _run_chat_and_wait_end(
                http_client, thread_id, "你好，请用一句话介绍自己"
            )
            assert result.run_end_status in ("done", "failed"), (
                f"运行未到达终态: {result.run_end_status}"
            )

            # 等待增量同步任务真的打到 mock 500 接口（证明失败路径被执行）。
            async def _hit_500() -> bool:
                return conv_500.called or msg_500.called

            try:
                await wait_until(
                    _hit_500,
                    timeout=60.0,
                    desc="云端 500 同步请求发出",
                )
            except TimeoutError as exc:
                raise AssertionError(
                    "run_end 后未在 60s 内观察到云同步请求（mock 500 未命中）"
                ) from exc

            # 给失败同步留出结算窗口，断言 sync_status 保持 pending。
            await asyncio.sleep(3.0)
            status_now = await _conversation_sync_status(
                http_client, db_path, thread_id
            )
            assert status_now == "pending", (
                f"云端同步接口返回 500 时 sync_status 不应离开 pending，"
                f"实际为 {status_now!r}"
            )

        # ---- 阶段 2：恢复 mock 200，再次触发同步，最终 synced ----
        with respx.mock:
            conv_ok = respx.post(path="/evolooplink/api/sync/conversation").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            msg_ok = respx.post(path="/evolooplink/api/sync/messages").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )

            result2 = await _run_chat_and_wait_end(
                http_client, thread_id, "再回复一次：今天天气如何"
            )
            assert result2.run_end_status in ("done", "failed"), (
                f"第二次运行未到达终态: {result2.run_end_status}"
            )

            async def _synced() -> bool:
                s = await _conversation_sync_status(
                    http_client, db_path, thread_id
                )
                return s == "synced"

            try:
                await wait_until(
                    _synced,
                    timeout=60.0,
                    desc="恢复 200 后 sync_status 变为 synced",
                )
            except TimeoutError as exc:
                raise AssertionError(
                    f"恢复 200 后 sync_status 未在 60s 内变为 synced，"
                    f"当前状态: "
                    f"{await _conversation_sync_status(http_client, db_path, thread_id)}"
                ) from exc

            assert conv_ok.called or msg_ok.called, (
                "恢复 200 后未观察到云同步请求"
            )
