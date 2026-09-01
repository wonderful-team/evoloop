"""真实火山引擎语音两种模式的分叉冒烟测试。

dialogue 模式 → ASR 定案路由到 Agent（run_agent_pipeline），并注册 TTS bridge
dictation 模式 → ASR 定案路由到听写润色（_handle_dictation_finalize）

下游用 recorder 桩断言调用（不启动 Agent 图），ASR 用系统真实 VolcAsrClient。
"""

from __future__ import annotations

import asyncio

import pytest

import app.api.routes.voice_ws as voice_ws
from app.core.voice.executor import active_volc_clients
from app.infrastructure.voice.volc_asr import VolcAsrClient
from tests.e2e.real._volc_helpers import (
    mp3_to_pcm16k,
    require_ffmpeg,
    tts_synthesize,
    volc_keys,
)

pytestmark = [pytest.mark.e2e, pytest.mark.real]

_VOLC_CONFIG = {
    "SEEDUPLEX_APP_ID": None,
    "SEEDUPLEX_ACCESS_KEY": None,
}


def _patch_config(monkeypatch: pytest.MonkeyPatch, app_id: str, access_key: str) -> None:
    _VOLC_CONFIG["SEEDUPLEX_APP_ID"] = app_id
    _VOLC_CONFIG["SEEDUPLEX_ACCESS_KEY"] = access_key
    monkeypatch.setattr(
        voice_ws.SystemConfigService,
        "get_value",
        staticmethod(lambda key, default=None: _VOLC_CONFIG.get(key, default)),
    )


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.event = asyncio.Event()

    async def record(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))
        self.event.set()


class _MockWs:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send_bytes(self, audio: bytes) -> None:
        self.sent.append(audio)

    async def send_json(self, data: dict) -> None:
        pass


async def _run_finalize(app_id, access_key, mode, thread_id, conn_id, ws, pcm_path) -> None:
    client = VolcAsrClient(app_id, access_key)
    await client.connect()
    with open(pcm_path, "rb") as f:
        while True:
            chunk = f.read(3200)
            if not chunk:
                break
            await client.send_audio(chunk)
    await voice_ws._finalize_asr_session(ws, client, thread_id, conn_id, mode=mode)
    await client.close()


class TestRealVoiceModes:
    @pytest.mark.timeout(90)
    async def test_dialogue_routes_to_agent_with_bridge(
        self, system_config, monkeypatch, tmp_path,
    ) -> None:
        """dialogue：ASR 定案 → run_agent_pipeline + VoiceTtsBridge 转发真实 TTS 音频。"""
        require_ffmpeg()
        app_id, access_key = volc_keys(system_config)
        _patch_config(monkeypatch, app_id, access_key)

        audio, _ = await tts_synthesize(app_id, access_key, "现在几点了")
        pcm = tmp_path / "in.pcm"
        mp3_to_pcm16k(audio, tmp_path / "in.mp3", pcm)

        agent = _Recorder()
        paste = _Recorder()
        monkeypatch.setattr(voice_ws, "run_agent_pipeline", agent.record)
        monkeypatch.setattr(voice_ws, "_handle_dictation_finalize", paste.record)
        ws = _MockWs()
        tid = "t-dialog-real"
        try:
            await _run_finalize(app_id, access_key, "dialogue", tid, "c-dialog", ws, pcm)
            await asyncio.wait_for(agent.event.wait(), 15)
            assert agent.calls, "dialogue 定案未路由到 run_agent_pipeline"
            recognized = agent.calls[0][0][2]
            assert any(n in recognized for n in ("几", "点")), f"ASR 识别异常: {recognized!r}"
            assert not paste.calls, "dialogue 不应触发听写润色"

            bridge = active_volc_clients.get(tid)
            assert isinstance(bridge, voice_ws.VoiceTtsBridge), f"应注册 VoiceTtsBridge，实际 {type(bridge).__name__}"
            await bridge.send_chat_tts_text(start=True, end=False, content="好的，正在查询")
            await bridge.send_chat_tts_text(start=False, end=True, content="")
            assert ws.sent and len(ws.sent[-1]) > 0, "bridge 未转发 TTS 音频"
        finally:
            active_volc_clients.pop(tid, None)

    @pytest.mark.timeout(90)
    async def test_dictation_routes_to_paste(
        self, system_config, monkeypatch, tmp_path,
    ) -> None:
        """dictation：ASR 定案 → _handle_dictation_finalize 携带原文，不触发 Agent。"""
        require_ffmpeg()
        app_id, access_key = volc_keys(system_config)
        _patch_config(monkeypatch, app_id, access_key)

        audio, _ = await tts_synthesize(app_id, access_key, "现在几点了")
        pcm = tmp_path / "in.pcm"
        mp3_to_pcm16k(audio, tmp_path / "in.mp3", pcm)

        agent = _Recorder()
        paste = _Recorder()
        monkeypatch.setattr(voice_ws, "run_agent_pipeline", agent.record)
        monkeypatch.setattr(voice_ws, "_handle_dictation_finalize", paste.record)
        ws = _MockWs()
        tid = "t-dict-real"
        try:
            await _run_finalize(app_id, access_key, "dictation", tid, "c-dict", ws, pcm)
            await asyncio.wait_for(paste.event.wait(), 15)
            assert paste.calls, "dictation 定案未路由到听写润色"
            body = paste.calls[0][0][0]
            assert any(n in body.get("raw_text", "") for n in ("几", "点")), f"原文异常: {body.get('raw_text')!r}"
            assert not agent.calls, "dictation 不应触发 Agent"
        finally:
            active_volc_clients.pop(tid, None)
