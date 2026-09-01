"""E2E：Rewind/Retry 跨域清理链路（对应文档第十五章、八.1、五）。

覆盖缺口：
  1. rewind 注销 pending 的 HITL 索密请求（十五.1 步骤二 cancel_request）
  2. retry 后 ContextHydrator/start_run 清理 final_outcome 等审计标记（八.3 / 五）
  3. rewind 触发记忆域清理（RewindRequestedEvent → MemoryRewind 删除记忆行）
  4. hitl.request 信封通道专属性：仅 MobileChannel 实现 send_hitl_request，
     VoiceChannel/WebChannel 为 no-op（base.py:64），voice WS 不应出现
     `voice.route_result {status: "blocked"}` 信封（八.1）

实现要点：
  - HITL 触发：提示词显式要求 LLM 调用 ask_human 工具（app/core/hitl/tools.py），
    通过 activity 端点 human_request 字段确认挂起；LLM 不配合时 skip。
  - 记忆写入：LLM 调用 remember 工具（app/core/memory/tools.py）落库 memory_index，
    source_run_id = run_id；rewind 后 MemoryRewind 按 run_id/source_message_id 删除。
  - 断言稳健性：环境不确定性一律 skip 不 fail；每个用例 timeout=180s。
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
    VoiceConn,
    collect_sse_until,
    observe_agent_run,
    wait_until,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real, pytest.mark.slow]

#: 显式要求 LLM 调用 ask_human 工具，触发 HITL 挂起（文档八.1）
#: 强制带 context 参数：回归覆盖 ask_human 的 context 与 i18n.get 的 context
#: 同名参数碰撞（曾导致 'str' object is not a mapping，见 TestHitlEnvelopeVoiceExclusivity）
HITL_PROMPT_TEMPLATE = (
    "请立即调用 ask_human 工具（这是自动化测试，不要回复普通文本，"
    "也不要调用其它工具）。参数：input_type='text'，"
    "context='自动化测试上下文 {marker}'，"
    "prompt='{marker}：请确认这是自动化测试，回复任意文本即可'。"
    "调用后停留在等待用户回复的状态。"
)

#: 显式要求 LLM 调用 remember 工具写入长期记忆（app/core/memory/tools.py）
REMEMBER_PROMPT_TEMPLATE = (
    "请调用 remember 工具记住一条信息，content 参数为 '{marker}'，"
    "然后告诉我你已经记住了。"
)

#: 确定性成功的 Agent 运行（test_14 先例：browser navigate about:blank）
BROWSER_NAVIGATE_PROMPT = (
    "请使用 browser 工具访问 about:blank 并确认页面加载成功。"
    "只需调用一次工具，然后返回成功信息。"
)


# ---------------------------------------------------------------------------
# SQLite 直读辅助（仅读取，不修改；参考 test_13/test_14 先例）
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
    base = (
        Path(os.path.expanduser(app_data_dir)).expanduser()
        if app_data_dir
        else Path.home() / ".evoloop"
    )
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


async def _activity_state(http_client: httpx.AsyncClient, tid: str) -> dict[str, Any]:
    """读取线程 activity 状态（含 human_request / final_outcome）。"""
    resp = await http_client.get(f"/api/v1/conversations/{tid}/activity", timeout=10.0)
    if resp.status_code != 200:
        return {}
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _wait_for_hitl_request(
    http_client: httpx.AsyncClient, tid: str, timeout: float = 60.0
) -> dict[str, Any]:
    """轮询 activity 端点直到出现挂起的 human_request。"""

    async def _has_hitl() -> dict[str, Any] | None:
        state = await _activity_state(http_client, tid)
        hr = state.get("human_request")
        return hr if hr else None

    return await wait_until(
        _has_hitl, timeout=timeout, interval=0.5, desc="HITL 请求挂起"
    )


async def _get_messages(
    http_client: httpx.AsyncClient, tid: str
) -> list[dict[str, Any]]:
    resp = await http_client.get(f"/api/v1/conversations/{tid}/messages", timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("data", [])


async def _find_human_message(
    http_client: httpx.AsyncClient, tid: str, prompt: str | None = None
) -> dict[str, Any] | None:
    """找到目标 human 消息：优先按内容精确匹配，否则取最早一条。"""
    messages = await _get_messages(http_client, tid)
    if prompt is not None:
        for m in messages:
            if m.get("role") == "human" and m.get("content") == prompt:
                return m
    for m in messages:
        if m.get("role") == "human":
            return m
    return None


async def _rewind(
    http_client: httpx.AsyncClient, tid: str, message_id: str
) -> dict[str, Any]:
    """POST /conversations/{tid}/rewind，断言成功并返回响应体。"""
    resp = await http_client.post(
        f"/api/v1/conversations/{tid}/rewind",
        json={"message_id": message_id, "revert_files": False},
        timeout=60.0,
    )
    assert resp.status_code == 200, f"rewind 失败: {resp.status_code} {resp.text}"
    return resp.json()


async def _cancel_hitl_best_effort(http_client: httpx.AsyncClient, tid: str) -> None:
    """测试收尾：尽力取消可能残留的 HITL 请求，避免后台任务永久挂起。"""
    try:
        await http_client.post(
            "/api/v1/hitl/cancel",
            json={"thread_id": tid, "reason": "e2e cleanup"},
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001 - cleanup 不允许影响用例结果
        logger.warning("HITL 清理失败 thread=%s: %s", tid, exc)


async def _run_simple_chat(
    http_client: httpx.AsyncClient,
    tid: str,
    prompt: str,
    timeout: float = 150.0,
) -> dict[str, Any]:
    """发起一次对话并等待 run_end，返回 run_end 数据。"""
    observer = asyncio.create_task(
        observe_agent_run(http_client, tid, timeout=timeout, expect_start=True)
    )
    await asyncio.sleep(0)
    resp = await http_client.post(
        "/api/v1/chat", json={"thread_id": tid, "message": prompt}
    )
    assert resp.status_code == 200, f"/chat 失败: {resp.status_code} {resp.text}"
    assert resp.json().get("status") == "queued", resp.text
    result = await observer
    return result.run_end.json if result.run_end else {}


# ---------------------------------------------------------------------------
# 用例 1：rewind 注销 pending HITL 请求
# ---------------------------------------------------------------------------


class TestRewindCancelsPendingHitl:
    """文档十五.1 步骤二：rewind 强行注销 pending 的 HITL 索密请求（cancel_request）。"""

    @pytest.mark.timeout(180)
    async def test_rewind_cancels_pending_hitl(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """HITL 挂起期间执行 rewind，断言 human_request 清除、DB 请求被置为 cancelled。"""
        marker = f"e2e-hitl-{uuid.uuid4().hex[:8]}"
        prompt = HITL_PROMPT_TEMPLATE.format(marker=marker)
        db_path = await _get_db_path(http_client)

        # 1. 订阅 SSE（HITL 触发即停），发起会调用 ask_human 的对话
        sse_task = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event in ("human_request", "run_end"),
                timeout=120.0,
                desc="HITL 触发事件（human_request 或 run_end）",
            )
        )
        await asyncio.sleep(0)
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": prompt}
        )
        assert resp.status_code == 200, resp.text

        # 2. 等待 HITL 挂起；LLM 未调用 ask_human 时 skip
        try:
            hr = await _wait_for_hitl_request(http_client, thread_id, timeout=60.0)
        except TimeoutError:
            pytest.skip("LLM 未在超时内调用 ask_human，无法稳定触发 HITL")
        assert hr.get("id"), f"human_request 缺少 id: {hr}"
        request_id = hr["id"]
        logger.info("HITL 已挂起 thread=%s request_id=%s", thread_id, request_id)

        # SSE 侧应出现过 human_request 事件
        try:
            events = await sse_task
        except TimeoutError:
            events = []
        sse_hitl = [ev for ev in events if ev.event == "human_request"]
        assert sse_hitl, "SSE 未观察到 human_request 事件（HITL 挂起但未推送前端）"

        try:
            # 3. 执行 rewind（目标为该次对话的 human 消息）
            human = await _find_human_message(http_client, thread_id, prompt)
            assert human is not None, "未找到触发 HITL 的 human 消息"
            body = await _rewind(http_client, thread_id, human["id"])
            assert body["status"] == "rewound", body
            assert body["removed_count"] >= 1, body

            # 4. activity 侧：human_request 应被清除
            async def _cleared() -> bool:
                state = await _activity_state(http_client, thread_id)
                return state.get("human_request") is None

            try:
                await wait_until(
                    _cleared, timeout=30.0, desc="rewind 后 activity.human_request 清除"
                )
            except TimeoutError as exc:
                raise AssertionError(
                    f"rewind 后 human_request 仍在挂起: {await _activity_state(http_client, thread_id)}"
                ) from exc

            # 5. DB 侧：该请求状态应为 cancelled（不再是 pending）
            async def _cancelled() -> bool:
                rows = await _query_db(
                    db_path,
                    "SELECT status FROM human_requests WHERE id = ?",
                    (request_id,),
                )
                return bool(rows) and rows[0]["status"] == "cancelled"

            try:
                await wait_until(
                    _cancelled, timeout=30.0, desc="DB human_requests 置为 cancelled"
                )
            except TimeoutError as exc:
                rows = await _query_db(
                    db_path,
                    "SELECT status FROM human_requests WHERE id = ?",
                    (request_id,),
                )
                raise AssertionError(
                    f"rewind 后 HITL 请求未取消: {[dict(r) for r in rows]}"
                ) from exc

            # 6. rewind 已删除目标 human 消息及其后的全部消息
            remaining = await _get_messages(http_client, thread_id)
            assert all(m.get("id") != human["id"] for m in remaining), (
                "rewind 后目标 human 消息应已被删除"
            )
        finally:
            await _cancel_hitl_best_effort(http_client, thread_id)


# ---------------------------------------------------------------------------
# 用例 2：retry 后审计标记清理
# ---------------------------------------------------------------------------


class TestRetryClearsAuditMarks:
    """文档八.3：retry 新 run 开始时 ContextHydrator/start_run 清理审计标记。"""

    @pytest.mark.timeout(180)
    async def test_retry_clears_audit_marks(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """首次成功 run 后 final_outcome=COMPLETED；retry 后新 run 开始时被清空。"""
        db_path = await _get_db_path(http_client)

        # 1. 第一次确定性成功的 run（browser navigate about:blank）
        run_end = await _run_simple_chat(
            http_client, thread_id, BROWSER_NAVIGATE_PROMPT
        )
        if run_end.get("status") != "done":
            pytest.skip(
                f"首次运行未成功完成(status={run_end.get('status')})，无法验证审计标记"
            )

        # 2. 等待审计落库 final_outcome=COMPLETED（文档五：FinishNode 审计）
        async def _completed() -> bool:
            rows = await _query_db(
                db_path,
                "SELECT final_outcome FROM agent_activities WHERE thread_id = ?",
                (thread_id,),
            )
            return (
                bool(rows) and (rows[0]["final_outcome"] or "").upper() == "COMPLETED"
            )

        try:
            await wait_until(
                _completed, timeout=90.0, desc="首次运行 final_outcome=COMPLETED"
            )
        except TimeoutError:
            pytest.skip(
                "首次运行审计未产生 final_outcome=COMPLETED，跳过审计标记清理验证"
            )

        human = await _find_human_message(
            http_client, thread_id, BROWSER_NAVIGATE_PROMPT
        )
        assert human is not None, "未找到首次运行的 human 消息"

        # 3. 订阅 SSE 观察 retry 新 run，发起 retry
        #    注意：retry 内部先执行 perform_rewind（_chat.py:247），旧 run 的
        #    run_end 会在新 run 的 run_start 之前发布（rewind 收尾事件）。
        #    因此不能用 observe_agent_run（它在首个 run_end 即停止），
        #    必须等 run_start 出现后再等 run_end。
        state: dict[str, bool] = {"started": False}

        def _retry_terminal(ev: Any) -> bool:
            if ev.event == "run_start":
                state["started"] = True
            return state["started"] and ev.event == "run_end"

        retry_observer = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                _retry_terminal,
                timeout=150.0,
                desc="retry 新 run 完成（run_start → run_end）",
            )
        )
        await asyncio.sleep(0)
        resp = await http_client.post(
            "/api/v1/chat/retry",
            json={
                "thread_id": thread_id,
                "message_id": human["id"],
                "message": "retry",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued", body
        assert body["action"] == "retry", body

        # 4. retry 新 run 开始时 final_outcome 应被清空（start_run 置 ""；
        #    ContextHydrator 同时清理 shadow_audit/verification）
        async def _cleared() -> bool:
            rows = await _query_db(
                db_path,
                "SELECT final_outcome FROM agent_activities WHERE thread_id = ?",
                (thread_id,),
            )
            return bool(rows) and (rows[0]["final_outcome"] or "") == ""

        try:
            await wait_until(
                _cleared,
                timeout=60.0,
                desc="retry 新 run 开始后 final_outcome 被清空",
            )
        except TimeoutError as exc:
            rows = await _query_db(
                db_path,
                "SELECT status, final_outcome FROM agent_activities WHERE thread_id = ?",
                (thread_id,),
            )
            raise AssertionError(
                f"retry 后新 run 开始时 final_outcome 未被清空: {[dict(r) for r in rows]}"
            ) from exc

        logger.info("retry 后 final_outcome 已被清空（= ''）")

        # 5. retry 新 run 应正常完成（done/failed 均为终态，LLM 结果有波动）
        retry_events = await retry_observer
        retry_run_end = [ev for ev in retry_events if ev.event == "run_end"][-1]
        retry_status = retry_run_end.json.get("status")
        assert retry_status in ("done", "failed"), (
            f"retry 新 run 终态异常: {retry_status}"
        )
        logger.info("retry 新 run 终态=%s", retry_status)


# ---------------------------------------------------------------------------
# 用例 3：rewind 触发记忆域清理
# ---------------------------------------------------------------------------


class TestRewindCleansMemoryDomain:
    """RewindRequestedEvent → MemoryRewind 删除受影响 run 的记忆行（memory_index）。

    2026-08 曾为 XFAIL：app 侧 MemoryRewind 用 filters={"run_id": ...} 过滤，
    但 MemoryIndex 无 run_id 列（仅 source_run_id），_db_search 静默丢弃该键后
    反而会返回全部记忆；且 search_memories 默认 member_id=0 与 remember 工具
    写入的 member_id=1 错配，导致记忆行永远无法清理。已修复
    （subscribers.py 改用 source_run_id 过滤 + member_id=None），现为常规用例。
    """

    @pytest.mark.timeout(180)
    async def test_rewind_cleans_memory_rows(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """remember 工具写入唯一标记记忆后 rewind，断言该记忆行被删除且不误删其它记忆。"""
        marker = f"e2e-mem-{uuid.uuid4().hex[:8]}"
        db_path = await _get_db_path(http_client)

        # 1. 记录 rewind 前全量记忆索引（用于校验不误删无关记忆）
        before_rows = await _query_db(
            db_path, "SELECT id, source_run_id FROM memory_index"
        )

        # 2. 发起会调用 remember 工具的对话
        prompt = REMEMBER_PROMPT_TEMPLATE.format(marker=marker)
        run_end = await _run_simple_chat(http_client, thread_id, prompt)
        if run_end.get("status") != "done":
            pytest.skip(f"remember 运行未成功完成(status={run_end.get('status')})")

        # 3. 等待带唯一标记的记忆行落库；LLM 未调用 remember 时 skip
        async def _mem_row() -> dict[str, Any] | None:
            rows = await _query_db(
                db_path,
                "SELECT id, source_run_id FROM memory_index WHERE title LIKE ? OR description LIKE ?",
                (f"%{marker}%", f"%{marker}%"),
            )
            return dict(rows[0]) if rows else None

        try:
            mem = await wait_until(
                _mem_row, timeout=60.0, desc=f"remember 记忆落库 {marker}"
            )
        except TimeoutError:
            pytest.skip("LLM 未调用 remember 工具或记忆未落库，无法验证记忆域清理")

        assert mem["source_run_id"], f"remember 记忆缺少 source_run_id: {mem}"

        human = await _find_human_message(http_client, thread_id, prompt)
        assert human is not None, "未找到 remember 运行的 human 消息"

        # 4. rewind 到该次运行之前
        body = await _rewind(http_client, thread_id, human["id"])
        assert body["status"] == "rewound", body
        assert body["removed_count"] >= 1, body

        # 5. 目标记忆行应被删除（MemoryRewind 按受影响 run 清理）
        async def _gone() -> bool:
            rows = await _query_db(
                db_path, "SELECT id FROM memory_index WHERE id = ?", (mem["id"],)
            )
            return not rows

        try:
            await wait_until(_gone, timeout=30.0, desc=f"rewind 删除记忆行 {mem['id']}")
        except TimeoutError as exc:
            raise AssertionError(
                f"rewind 后记忆行 {mem['id']}（run={mem['source_run_id']}）仍存在"
            ) from exc

        # 6. 跨域清理不应误删无关记忆：非本 run 的既有记忆行应原样保留。
        #    注意：rewind 的删除范围是受影响 message/run，无关行消失即缺陷。
        after_rows = await _query_db(db_path, "SELECT id FROM memory_index")
        after_ids = {r["id"] for r in after_rows}
        unrelated = [
            r["id"]
            for r in before_rows
            if r["source_run_id"] and r["source_run_id"] != mem["source_run_id"]
        ]
        removed_unrelated = [i for i in unrelated if i not in after_ids]
        assert not removed_unrelated, (
            f"rewind 误删了 {len(removed_unrelated)} 条无关记忆行"
            f"（受影响 run={mem['source_run_id']}）: {removed_unrelated[:10]}"
        )


# ---------------------------------------------------------------------------
# 用例 4：hitl.request 信封通道专属性（voice WS 不应出现 blocked 信封）
# ---------------------------------------------------------------------------


class TestHitlEnvelopeVoiceExclusivity:
    """文档八.1：仅 MobileChannel 实现 send_hitl_request；VoiceChannel 为 no-op。"""

    @pytest.mark.timeout(180)
    async def test_voice_ws_gets_no_blocked_envelope(
        self,
        voice_conn: VoiceConn,
        http_client: httpx.AsyncClient,
        thread_id: str,
    ) -> None:
        """voice 会话触发 HITL 挂起：web SSE 出现 human_request，voice WS 无 blocked 信封。"""
        marker = f"e2e-vhitl-{uuid.uuid4().hex[:8]}"
        prompt = HITL_PROMPT_TEMPLATE.format(marker=marker)

        # 1. 订阅 web SSE（观察 human_request 事件）
        sse_task = asyncio.create_task(
            collect_sse_until(
                http_client,
                f"/api/v1/stream/chat/{thread_id}",
                lambda ev: ev.event in ("human_request", "run_end"),
                timeout=120.0,
                desc="voice 会话 HITL 触发事件",
            )
        )
        await asyncio.sleep(0)

        # 2. 通过 voice.route 触发 agent 运行（绑定 voice WS 到该 thread）
        await voice_conn.send_route(prompt)

        # 3. 等待 HITL 挂起
        try:
            hr = await _wait_for_hitl_request(http_client, thread_id, timeout=60.0)
        except TimeoutError:
            await _cancel_hitl_best_effort(http_client, thread_id)
            pytest.skip("LLM 未在超时内调用 ask_human，无法稳定触发 HITL")
        assert hr.get("id"), f"human_request 缺少 id: {hr}"
        logger.info(
            "voice 会话 HITL 已挂起 thread=%s request_id=%s", thread_id, hr["id"]
        )

        try:
            # 4. HITL 挂起期间保持 voice WS 打开，收集信封（等待窗口 12s）
            await asyncio.sleep(12.0)
            envelopes = voice_conn.collected_events

            # 5. 负向断言：voice WS 不应出现 blocked 路由结果信封
            blocked = [
                env
                for env in envelopes
                if env.get("type") == "voice.route_result"
                and env.get("body", {}).get("status") == "blocked"
            ]
            assert not blocked, (
                f"voice WS 出现了不应存在的 blocked 信封: {json.dumps(blocked, ensure_ascii=False)}"
            )

            # 6. web SSE 侧应观察到 human_request 事件
            try:
                events = await sse_task
            except TimeoutError:
                events = []
            sse_hitl = [ev for ev in events if ev.event == "human_request"]
            assert sse_hitl, (
                "web SSE 未观察到 human_request 事件（HITL 未推送到 web 端）"
            )
            logger.info(
                "voice WS 挂起期间信封类型: %s", [e.get("type") for e in envelopes]
            )
        finally:
            await _cancel_hitl_best_effort(http_client, thread_id)

        # 7. 取消恢复后：断言该 thread 无工具错误落库。
        #    回归保障：ask_human 的 context 参数与 i18n.get 的 context 参数
        #    同名碰撞，曾导致 LLM 带 context 再次调用 ask_human 时抛
        #    'str' object is not a mapping 并被持久化为 tool 消息
        #    （测试先前因只断言首次挂起而漏检）。
        db_path = await _get_db_path(http_client)

        async def _no_error_rows() -> bool:
            rows = await _query_db(
                db_path,
                "SELECT COUNT(*) AS n FROM messages "
                "WHERE thread_id = ? AND content LIKE ?",
                (thread_id, "%Error%"),
            )
            return rows and rows[0]["n"] == 0

        try:
            await wait_until(
                _no_error_rows, timeout=60.0, desc="取消恢复后无错误消息落库"
            )
        except TimeoutError as exc:
            raise AssertionError(
                "取消恢复后存在错误消息落库（ask_human context 参数碰撞回归）"
            ) from exc
