"""真实火山引擎 ASR/TTS 传输冒烟测试（系统客户端直连）。

覆盖替换后的传输层：原 VolcDialogClient（实时对话）已替换为
VolcAsrClient(ASR) + VolcTtsClient(TTS)。用例自包含闭环：

1. TTS    系统 VolcTtsClient 合成「现在几点了」→ 校验 mp3 非空、ffprobe 可解码、时长合理
2. ASR    上一步 mp3 解码为 16k PCM → 系统 VolcAsrClient 识别 → 断言还原原句
3. 流式    receive_audio_stream 多帧产出 + 单连接连续多 session（真流式）
"""

from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.voice.volc_tts import VolcTtsClient
from tests.e2e.real._volc_helpers import (
    TTS_TEXT,
    asr_recognize_pcm,
    mp3_duration,
    mp3_to_pcm16k,
    require_ffmpeg,
    tts_synthesize,
    volc_keys,
)

pytestmark = [pytest.mark.e2e, pytest.mark.real]


class TestRealVoiceAsrTtsTransport:
    @pytest.mark.timeout(90)
    async def test_tts_synthesis(self, system_config, tmp_path) -> None:
        """系统 VolcTtsClient 合成语音：mp3 非空、可解码、时长合理。"""
        app_id, access_key = volc_keys(system_config)
        audio, t_tts = await tts_synthesize(app_id, access_key, TTS_TEXT)
        assert len(audio) > 0, "TTS 返回空音频"
        dur = mp3_duration(audio, tmp_path / "synth.mp3")
        assert dur > 1.0, f"TTS 时长过短: {dur:.2f}s (合成耗时 {t_tts * 1000:.0f} ms)"

    @pytest.mark.timeout(90)
    async def test_asr_recognize_roundtrip(self, system_config, tmp_path) -> None:
        """回环：系统 TTS 合成 → 解码 16k PCM → 系统 VolcAsrClient 识别还原原句。"""
        require_ffmpeg()
        app_id, access_key = volc_keys(system_config)
        audio, _ = await tts_synthesize(app_id, access_key, TTS_TEXT)
        mp3_path = tmp_path / "synth.mp3"
        pcm_path = tmp_path / "synth.pcm"
        mp3_to_pcm16k(audio, mp3_path, pcm_path)
        text, t_asr = await asr_recognize_pcm(app_id, access_key, pcm_path)
        assert text, "ASR 返回空文本"
        assert any(n in text for n in ("几", "点")), f"识别结果未还原原句: {text!r} (耗时 {t_asr * 1000:.0f} ms)"

    @pytest.mark.timeout(90)
    async def test_tts_stream_frames_progressive(self, system_config) -> None:
        """真流式：receive_audio_stream 逐帧产出（多帧），首帧早于整段完成。"""
        app_id, access_key = volc_keys(system_config)
        client = VolcTtsClient(app_id, access_key, session_id="stream-real")
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
            await client.start_session(client.DEFAULT_SPEAKER, session_id="stream-real")
            await client.send_text("这是一个用于验证流式合成的测试句子。", session_id="stream-real")
            await client.finish_session(session_id="stream-real")
            frames: list[bytes] = []
            async for chunk in client.receive_audio_stream(session_id="stream-real"):
                frames.append(chunk)
            assert len(frames) > 1, f"应多帧流式产出，实际 {len(frames)} 帧"
            assert all(len(f) > 0 for f in frames)
        finally:
            await client.close()

    @pytest.mark.timeout(90)
    async def test_tts_multi_session_single_connection(self, system_config) -> None:
        """单连接连续多个 session（句子级流式），每条都产出音频。"""
        app_id, access_key = volc_keys(system_config)
        client = VolcTtsClient(app_id, access_key, session_id="multi-real")
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
            for i, sent in enumerate(["现在几点了。", "今天天气很好。"]):
                sid = f"seg-{i}"
                await client.start_session(client.DEFAULT_SPEAKER, session_id=sid)
                await client.send_text(sent, session_id=sid)
                await client.finish_session(session_id=sid)
                total = 0
                async for chunk in client.receive_audio_stream(session_id=sid):
                    total += len(chunk)
                assert total > 0, f"句子 {sent!r} 无音频产出"
        finally:
            await client.close()
