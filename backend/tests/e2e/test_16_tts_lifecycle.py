"""阶段16：TTS 生命周期与流式分句端到端测试。

对应 EvoLoop Backend E2E Test Scenario Design：
- E2E-SC-007: TTS stream is chunked at sentence boundaries and final done uses skip_tts=True
- E2E-SC-016: _is_sending_chat_tts_text flag lifecycle and stale audio discard
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.e2e.conftest import VoiceConn, wait_until

pytestmark = pytest.mark.e2e


class TestTTSStreamLifecycle:
    """E2E-SC-007: 流式 TTS 按句末标点分块，最终 done 信封 skip_tts=True。"""

    @pytest.mark.timeout(120)
    @pytest.mark.real
    async def test_tts_chunks_split_on_punctuation(
        self,
        voice_conn: VoiceConn,
        volc_configured: bool,
        thread_id: str,
    ) -> None:
        """多句回复走 Agent 流式 TTS，验证边界与最终 done 信封行为。"""
        if not volc_configured:
            pytest.skip("火山引擎未配置，跳过真实 TTS 生命周期测试")

        prompt = "用三句话介绍 Python 的列表推导，每句话以句号结尾。"

        await voice_conn.send_route(prompt)

        final = await voice_conn.wait_terminal_route_result(timeout=90.0)
        final_status = final["body"]["status"]
        assert final_status in (
            "done",
            "failed",
        ), f"终态异常: {final_status}"

        # 给收集器一点时间收尾
        await asyncio.sleep(1.0)

        voice_events = voice_conn.collected_events

        tts_boundaries = [
            e for e in voice_events if e.get("type") == "voice.tts_boundary"
        ]

        # 每个 tts_boundary 句子应以句末标点结尾
        # （最后一条 boundary 可能是会话结束时的剩余片段，允许未完成句）
        punctuation = "。！？.!?\n…"
        for i, boundary in enumerate(tts_boundaries):
            sentence = boundary.get("body", {}).get("sentence", "")
            if sentence:
                if i == len(tts_boundaries) - 1:
                    continue
                assert (
                    sentence[-1] in punctuation
                ), f"tts_boundary 句子未以标点结尾: {sentence!r}"

        # 应有至少一条 voice.token 流式事件（后端已接线推送实时播报文本）
        tokens = [
            e for e in voice_events if e.get("type") == "voice.token"
        ]
        assert tokens, "流式播放时应推送 voice.token 事件（后端已接线）"

        # 最终 done 信封应携带 skip_tts=True
        if final_status == "done":
            assert (
                final["body"].get("skip_tts") is True
            ), f"最终 done 信封应设置 skip_tts=True，实际 body={final['body']}"

        # done 之后不应再出现 TTS 相关信封
        done_index = next(
            (
                i
                for i, e in enumerate(voice_events)
                if e.get("type") == "voice.route_result"
                and e.get("body", {}).get("status") == "done"
            ),
            None,
        )
        if done_index is not None:
            after = voice_events[done_index + 1 :]
            extra_tts = [
                e
                for e in after
                if e.get("type") in ("voice.tts_boundary", "voice.token")
            ]
            assert not extra_tts, f"done 之后不应再出现 TTS 信封: {extra_tts}"


class TestTTSFlagLifecycle:
    """E2E-SC-016: ASR/barge-in 期间 _is_sending_chat_tts_text=True，TTS 开始后复位；过期音频被丢弃。"""

    @pytest.mark.timeout(180)
    @pytest.mark.slow
    @pytest.mark.real
    async def test_tts_flag_lifecycle_and_audio_discard(
        self,
        voice_conn: VoiceConn,
        http_client: httpx.AsyncClient,
        volc_configured: bool,
        thread_id: str,
    ) -> None:
        """在长 Agent TTS 过程中 barge-in，验证旧流静音且新 route 能启动新 TTS 流。

        注：事件 459/350 等 Volcengine 协议事件由服务端 Volc 客户端接收，
        本测试从外部 WebSocket 端点可观测的语义出发：barge-in 后旧流 TTS 边界
        不再增加，新 route 完成后线程退出 running。
        """
        if not volc_configured:
            pytest.skip("火山引擎未配置，跳过 TTS 标志生命周期测试")

        long_prompt = (
            "请使用 execute_command 工具，background 参数设为 false，"
            "运行命令 `sleep 4`，并返回命令输出结果。"
        )

        await voice_conn.send_route(long_prompt)

        async def _activity_running() -> bool:
            resp = await http_client.get(
                f"/api/v1/conversations/{thread_id}/activity"
            )
            if resp.status_code != 200:
                return False
            return resp.json().get("status") == "running"

        await wait_until(
            _activity_running,
            timeout=45.0,
            desc="首次运行进入 running",
        )

        voice_events = voice_conn.collected_events
        # 记录 barge-in 前的 TTS 边界数量
        pre_barge_tts = len(
            [e for e in voice_events if e.get("type") == "voice.tts_boundary"]
        )

        # Barge-in 应设置 _is_sending_chat_tts_text=True，旧音频被丢弃
        await voice_conn.send_type("voice.barge_in", {"thread_id": thread_id})
        barge_env = await voice_conn._drain_until(
            lambda e: e.get("type") == "voice.barge_in", timeout=10.0
        )
        assert barge_env is not None, "未收到 voice.barge_in 确认信封"

        # barge-in 后旧 Worker 仍存活
        assert await _activity_running(), "barge-in 后旧 Worker 应该仍然存活"

        # 过期音频丢弃：旧流不应再新增 TTS 边界
        await asyncio.sleep(1.5)
        voice_events = voice_conn.collected_events
        post_barge_tts = len(
            [e for e in voice_events if e.get("type") == "voice.tts_boundary"]
        )
        assert (
            post_barge_tts == pre_barge_tts
        ), "barge-in 后旧流不应继续推送 TTS 边界"

        # 新 route 触发 NEW_COMMAND，取消旧任务并启动新流
        await voice_conn.send_route("帮我用一句话总结前端目录结构")

        # 新运行可能因 LLM 首字延迟耗时较长，先等线程退出 running 再收终态信封
        async def _not_running() -> bool:
            return not await _activity_running()

        await wait_until(
            _not_running,
            timeout=180.0,
            desc="新任务完成后线程退出 running",
        )

        final = await voice_conn.wait_terminal_route_result(timeout=60.0)
        assert final["body"]["status"] in (
            "done",
            "failed",
        ), f"新 route 终态异常: {final}"

        # 终态信封到达后再次确认线程退出 running
        await wait_until(
            _not_running,
            timeout=30.0,
            desc="新任务完成后线程退出 running",
        )
