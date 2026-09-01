"""VoiceTtsBridge 单元测试（mock VolcTtsClient，无真实网络）。

覆盖预连接、同连接复用、替换时关闭旧连接（防泄漏）、逐帧转发、空文本跳过。
"""

from __future__ import annotations

import pytest

import app.api.routes.voice_ws as voice_ws
from app.core.voice.executor import active_volc_clients

pytestmark = pytest.mark.unit

_KEYS = {
    "SEEDUPLEX_APP_ID": "app-id",
    "SEEDUPLEX_ACCESS_KEY": "access-key",
}


class FakeVolcTts:
    """最小可用的 VolcTtsClient 替身，记录实例与关闭状态。"""

    DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"
    instances: list[FakeVolcTts] = []

    def __init__(self, app_id: str, access_key: str, session_id: str | None = None) -> None:
        self.app_id = app_id
        self.access_key = access_key
        self.session_id = session_id
        self.ws: object = object()
        self.closed = False
        self.sent_texts: list[str] = []
        FakeVolcTts.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True
        self.ws = None

    async def start_session(
        self, speaker: str, sample_rate: int = 24000, session_id: str | None = None, format: str = "mp3"
    ) -> None:
        pass

    async def send_text(self, text: str, session_id: str | None = None) -> None:
        self.sent_texts.append(text)

    async def finish_session(self, session_id: str | None = None) -> None:
        pass

    async def receive_audio_stream(self, timeout: float = 30.0, session_id: str | None = None):
        yield b"\xff\xe0\x00\x10" * 100
        yield b"\xff\xe0\x00\x10" * 100


@pytest.fixture(autouse=True)
def _patch_deps(monkeypatch):
    FakeVolcTts.reset()
    monkeypatch.setattr(
        voice_ws.SystemConfigService,
        "get_value",
        staticmethod(lambda key, default=None: _KEYS.get(key, default)),
    )
    monkeypatch.setattr(voice_ws, "VolcTtsClient", FakeVolcTts)
    yield
    active_volc_clients.clear()


class _MockWs:
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def send_bytes(self, audio: bytes) -> None:
        self.audio.append(audio)

    async def send_json(self, data: dict) -> None:
        pass


class TestVoiceTtsBridge:
    async def test_preconnect_establishes_client(self) -> None:
        bridge = voice_ws.VoiceTtsBridge("t", "c1", lambda a: None)
        await bridge.connect()
        assert bridge._client is not None
        assert bridge._client.ws is not None
        await bridge.close()
        assert bridge._client is None

    async def test_register_reuses_same_conn(self) -> None:
        """同 conn 重复注册 → 复用同一 bridge，只建 1 条连接。"""
        ws = _MockWs()
        await voice_ws._register_dialogue_tts_bridge("t", "c1", ws)
        b1 = active_volc_clients["t"]
        assert FakeVolcTts.instances, "预连接应建立客户端"
        await voice_ws._register_dialogue_tts_bridge("t", "c1", ws)
        assert active_volc_clients["t"] is b1, "同 conn 应复用，不重建"
        assert len(FakeVolcTts.instances) == 1, "只应建立一条连接"

    async def test_register_replace_closes_old(self) -> None:
        """换 conn（Rust 重连）→ 替换并关闭旧连接（防泄漏）。"""
        ws = _MockWs()
        await voice_ws._register_dialogue_tts_bridge("t", "c1", ws)
        old_client = active_volc_clients["t"]._client
        await voice_ws._register_dialogue_tts_bridge("t", "c2", ws)
        new_bridge = active_volc_clients["t"]
        assert new_bridge.conn_id == "c2"
        assert old_client.closed, "旧连接应被关闭"
        assert len(FakeVolcTts.instances) == 2

    async def test_send_streams_audio_frames(self) -> None:
        """send_chat_tts_text → 立即合成并逐帧转发（多帧）。"""
        ws = _MockWs()
        bridge = voice_ws.VoiceTtsBridge("t", "c1", lambda a: ws.send_bytes(a))
        await bridge.connect()
        await bridge.send_chat_tts_text(start=True, end=False, content="好的")
        assert len(ws.audio) == 2, f"应逐帧转发 2 帧，实际 {len(ws.audio)}"
        assert all(len(f) > 0 for f in ws.audio)
        assert FakeVolcTts.instances[0].sent_texts == ["好的"]
        await bridge.close()

    async def test_empty_text_noop(self) -> None:
        """空内容/纯空白 → 不合成不转发。"""
        ws = _MockWs()
        bridge = voice_ws.VoiceTtsBridge("t", "c1", lambda a: ws.send_bytes(a))
        await bridge.connect()
        await bridge.send_chat_tts_text(start=False, end=True, content="")
        await bridge.send_chat_tts_text(start=False, end=False, content="  ")
        assert not ws.audio
        await bridge.close()
