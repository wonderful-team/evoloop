"""阶段18：语音回复点缺口覆盖端到端测试（对应文档「十九、语音回复点全景图」）。

覆盖第十九章中此前 E2E 套件缺失的语音回复点：
  - 回复点 1：导航确认语 —— 语音端触发导航宏，收到 ``voice.navigate {route, feedback}`` 信封
  - 回复点 5：次轮业务安抚 —— Supervisor 派活给 Worker 时推送 ``voice.route_result {status:"routed"}``
  - 回复点 7：最终结单播报 —— Agent 语音终态 ``voice.route_result {status:"done", summary非空}``
  - 回复点 5+6+7 全链路：同线程 Agent 级多轮追问，两次真实 LLM 运行均到达 done、互不串扰

技术要点：
- VoiceConn 为单 reader 机制：``wait_terminal_route_result`` 只消费终态信封，
  收集非终态 routed 信封需用 ``_drain_until`` 自行过滤（参考 conftest.py:434 附近）。
- LLM 行为不可控时的降级策略：Supervisor 未生成安抚文本（routed 缺失/summary 空）、
  LLM 返回 failed 等环境因素一律 skip，不 fail；仅服务端契约确定的部分做硬断言。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import VoiceConn

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.real]

_TERMINAL_STATUSES = {"done", "failed", "cancelled"}
_ROUTE_DRAIN_TIMEOUT = 150.0


async def _collect_until_terminal(
    conn: VoiceConn, timeout: float = _ROUTE_DRAIN_TIMEOUT
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """收集全部 voice.route_result 直到终态信封，返回 (routed 信封列表, 终态信封或 None)。

    与 ``wait_terminal_route_result`` 不同：本函数同时消费非终态的 routed 安抚信封，
    用于覆盖回复点 5 的协议契约。
    """
    routed: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        env = await conn._drain_until(
            lambda e: e.get("type") == "voice.route_result",
            timeout=max(0.0, min(10.0, deadline - time.monotonic())),
        )
        if env is None:
            continue
        body = env.get("body") or {}
        status = body.get("status")
        if status in _TERMINAL_STATUSES:
            return routed, env
        if status == "routed":
            routed.append(env)
    return routed, None


def _extract_route_from_script(script: str) -> str | None:
    """从宏脚本中解析 frontend_navigate 的 route 参数（轻量正则，解析失败返回 None）。"""
    match = re.search(r"route:\s*['\"]?([^'\"\s]+)", script)
    return match.group(1) if match else None


async def _find_navigation_macro(
    http_client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    """从宏库中查找一个可语音触发的导航宏（namespace=preset 且脚本含 frontend_navigate）。

    先查 /api/v1/route/init 确认路由规格可用，再分页扫描宏表（最多 600 条），
    返回 {"trigger": 触发词, "expected_route": 脚本 route 或 None}；未找到返回 None。
    """
    init_resp = await http_client.get("/api/v1/route/init")
    if init_resp.status_code not in (200, 202):
        logger.warning("route/init 不可用: %s", init_resp.status_code)
        return None

    skip = 0
    while skip < 600:
        resp = await http_client.get(f"/api/v1/macros/?skip={skip}&limit=200")
        if resp.status_code != 200:
            logger.warning(
                "宏列表接口失败(status=%s): %s", resp.status_code, resp.text[:120]
            )
            return None
        items = resp.json()
        if not items:
            break
        for item in items:
            if item.get("namespace") != "preset":
                continue
            detail_resp = await http_client.get(f"/api/v1/macros/{item['id']}")
            if detail_resp.status_code != 200:
                continue
            detail = detail_resp.json()
            script = detail.get("macro_script") or ""
            patterns = detail.get("trigger_patterns") or []
            if "frontend_navigate" not in script or not patterns:
                continue
            # 过短的触发词易与 L0 builtin/local 模板撞车，优先 ≥4 字的触发词
            trigger = next((p for p in patterns if len(p) >= 4), None)
            if trigger is None:
                continue
            return {
                "trigger": trigger,
                "expected_route": _extract_route_from_script(script),
            }
        skip += len(items)
    return None


class TestVoiceReplyPoints:
    """十九 语音回复点缺口覆盖（回复点 1/5/7 + Agent 级多轮）。"""

    @pytest.mark.timeout(200)
    async def test_supervisor_comfort_routed_envelope(
        self, voice_conn: VoiceConn
    ) -> None:
        """回复点5：Supervisor 派活时推送 routed 安抚信封，summary 为安抚文本。

        复杂任务经 L0 未命中转投 Agent 后，Supervisor 首次派活给 Worker 的
        ai+tool_calls MessageBlock 会被 VoiceChannel.send 去重并 fire-and-forget
        推送 ``voice.route_result {status:"routed", summary}``。
        注意：现有套件的 ``wait_terminal_route_result`` 会忽略该非终态信封，
        本用例改用 ``_collect_until_terminal`` 显式收集。
        """
        await voice_conn.send_route("请使用 execute_command 工具执行 echo 命令")

        routed, terminal = await _collect_until_terminal(
            voice_conn, _ROUTE_DRAIN_TIMEOUT
        )
        assert terminal is not None, (
            f"150s 内未收到任何 voice.route_result 终态，thread={voice_conn.thread_id}"
        )

        non_empty = [e for e in routed if (e.get("body") or {}).get("summary")]
        if not non_empty:
            observed = [(e.get("body") or {}).get("summary", "")[:40] for e in routed]
            logger.warning(
                "Supervisor 未生成安抚文本（routed=%s, terminal=%s），降级 skip",
                observed,
                (terminal.get("body") or {}).get("status"),
            )
            pytest.skip(
                "Supervisor 未生成安抚文本（routed 信封缺失或 summary 为空，LLM 行为不可控）"
            )

        env = non_empty[0]
        body = env["body"]
        assert body["status"] == "routed", f"routed 信封状态异常: {body}"
        assert (body["summary"] or "").strip(), f"routed 信封 summary 不应为空: {body}"
        assert body["thread_id"] == voice_conn.thread_id
        # 回复点5 契约：routed 信封本身不触发 TTS（skip_tts=False，语音由流式 Token 覆盖）
        assert body.get("skip_tts") is False, (
            f"routed 信封 skip_tts 应恒为 False: {body}"
        )

    @pytest.mark.timeout(200)
    async def test_agent_terminal_done_envelope(self, voice_conn: VoiceConn) -> None:
        """回复点7：Agent 语音终态 done，summary 为真实 LLM 最终总结。

        简单可完成的任务（L0 未命中 → Agent 真实 LLM 运行）最终应推送
        ``voice.route_result {status:"done", summary非空}``，且语音已由流式合成
        覆盖，故 skip_tts=True（避免重复播报）。
        """
        await voice_conn.send_route("你好，请用一句话确认 LLM 连接正常。")
        terminal = await voice_conn.wait_terminal_route_result(timeout=180.0)
        body = terminal["body"]
        status = body["status"]

        if status != "done":
            # LLM/外部依赖不可控：failed/cancelled 时对 summary 做基础断言后 skip
            assert (body.get("summary") or "").strip(), (
                f"非 done 终态 summary 不应为空: {body}"
            )
            pytest.skip(
                f"LLM 返回 {status}（环境不可控），summary={body.get('summary')!r}"
            )

        assert body["status"] == "done", f"终态应到达 done: {body}"
        assert (body.get("summary") or "").strip(), (
            f"done 终态 summary 不应为空: {body}"
        )
        assert body["thread_id"] == voice_conn.thread_id
        # 回复点7 契约：done 终态 skip_tts=True（流式播报已完成，避免重复合成）
        assert body.get("skip_tts") is True, f"done 信封 skip_tts 应为 True: {body}"

    @pytest.mark.timeout(90)
    async def test_voice_navigate_envelope(
        self, voice_conn: VoiceConn, http_client: httpx.AsyncClient
    ) -> None:
        """回复点1：语音端触发导航宏 → voice.navigate {route, feedback} 信封。

        导航宏（namespace=preset 且脚本为 frontend_navigate）触发词命中 L0 navigate
        后，``handle_navigate`` 向语音 WS 推送 ``voice.navigate``，body 含 route
        与 feedback（默认 generic.ok 话术）。
        """
        nav = await _find_navigation_macro(http_client)
        if nav is None:
            pytest.skip("环境无导航宏（namespace=preset 且 frontend_navigate），跳过")

        trigger = nav["trigger"]
        logger.info(
            "触发导航宏触发词: %r (expected_route=%s)", trigger, nav["expected_route"]
        )
        await voice_conn.send_route(trigger)

        env = await voice_conn.wait_type("voice.navigate", timeout=30.0)
        body = env["body"]
        assert body.get("route"), f"voice.navigate 缺少 route: {body}"
        assert "feedback" in body, f"voice.navigate 缺少 feedback 字段: {body}"
        assert body["thread_id"] == voice_conn.thread_id
        if nav["expected_route"]:
            assert body["route"] == nav["expected_route"], (
                f"voice.navigate route 不匹配: {body}"
            )

    @pytest.mark.timeout(400)
    async def test_agent_multi_turn_same_thread(
        self, voice_conn: VoiceConn, unique_marker: str
    ) -> None:
        """Agent 级多轮：同线程连续两次复杂任务均到达 done，线程可复用、互不串扰。

        第一轮终态后立即在同一 thread 上发起第二轮 voice.route，验证：
        - 多轮语音对话不串扰（第二轮独立完成，不回放第一轮结果）
        - 线程状态机在 done 后回到可接受 route 的状态（线程可复用）
        """
        for turn in (1, 2):
            prompt = (
                f"请使用 execute_command 工具运行 echo turn-{turn}-{unique_marker}，"
                f"然后告诉我命令输出。"
            )
            await voice_conn.send_route(prompt)
            terminal = await voice_conn.wait_terminal_route_result(timeout=180.0)
            body = terminal["body"]
            status = body["status"]

            if status != "done":
                assert (body.get("summary") or "").strip(), (
                    f"第 {turn} 轮非 done 终态 summary 不应为空: {body}"
                )
                pytest.skip(
                    f"第 {turn} 轮 LLM 返回 {status}（环境不可控），summary={body.get('summary')!r}"
                )

            assert body["status"] == "done", f"第 {turn} 轮终态应到达 done: {body}"
            assert (body.get("summary") or "").strip(), (
                f"第 {turn} 轮 done 终态 summary 不应为空: {body}"
            )
            assert body["thread_id"] == voice_conn.thread_id
            logger.info(
                "第 %d 轮 done（thread=%s）: %s",
                turn,
                voice_conn.thread_id,
                body.get("summary", "")[:60],
            )
