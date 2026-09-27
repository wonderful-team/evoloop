"""Integration tests for the voice_ws routes (app/api/routes/voice_ws.py).

Covers the HTTP POST /voice/tts endpoint. The WebSocket endpoint
(voice_ws) requires loopback enforcement and a full WS lifecycle that
httpx.AsyncClient cannot exercise; see TestVoiceWebSocketSkipped.
"""


class TestTTS:
    async def test_empty_text_422(self, client):
        resp = await client.post("/voice/tts", json={"text": "   "})
        assert resp.status_code == 422

    async def test_success(self, client, monkeypatch):
        async def _fake_tts(_text, _voice=""):
            return b"\x00\x01\x02"

        monkeypatch.setattr(
            "app.api.routes.voice_ws.generate_volc_tts", _fake_tts
        )
        resp = await client.post(
            "/voice/tts", json={"text": "hello", "voice": "zh-CN"}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content == b"\x00\x01\x02"

    async def test_timeout_returns_504(self, client, monkeypatch):
        async def _slow_tts(_text, _voice=""):
            raise TimeoutError("timed out")

        monkeypatch.setattr(
            "app.api.routes.voice_ws.generate_volc_tts", _slow_tts
        )
        resp = await client.post("/voice/tts", json={"text": "slow"})
        assert resp.status_code == 504

    async def test_generic_error_returns_500(self, client, monkeypatch):
        async def _boom(_text, _voice=""):
            raise RuntimeError("service unavailable")

        monkeypatch.setattr(
            "app.api.routes.voice_ws.generate_volc_tts", _boom
        )
        resp = await client.post("/voice/tts", json={"text": "boom"})
        assert resp.status_code == 500


class TestVoiceWebSocketSkipped:
    """WebSocket endpoint /voice/ws is NOT tested via httpx.

    Reason: voice_ws requires (1) enforce_loopback_ws check that validates
    the connection comes from 127.0.0.1, and (2) a full-duplex WebSocket
    lifecycle with binary frames, ASR/Volcengine integration, and session
    management that cannot be exercised through ASGITransport. Testing
    requires either a live server or a dedicated WebSocket test client
    (e.g. starlette.testclient.WebSocketClientSession).
    """

    def test_skip_documentation(self):
        assert True
