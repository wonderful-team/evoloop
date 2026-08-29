"""Volcengine v3 bidirectional streaming TTS client.

Protocol: wss://openspeech.bytedance.com/api/v3/tts/bidirection
Text streaming in, audio (mp3) streaming out over a single WebSocket.

Flow (binary frames, see volc_protocol.parse_response):
  StartConnection(1) -> StartSession(100, speaker+audio_params)
  -> TaskRequest(200, text) -> FinishSession(102)
  -> audio frames TTS_RESPONSE(352) ... SESSION_FINISHED(152)
"""

import asyncio
import json
import logging
import ssl
import uuid
from collections.abc import AsyncIterator
from typing import Any

import websockets

from app.infrastructure.voice import volc_protocol as protocol

logger = logging.getLogger(__name__)

VOLC_TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
VOLC_TTS_RESOURCE_ID = "seed-tts-2.0"
DEFAULT_VOLC_SPEAKER = "zh_female_vv_uranus_bigtts"


def _frame(event: int, payload: dict[str, Any], session_id: str = "") -> bytes:
    payload_bytes = str.encode(json.dumps(payload))
    frame = bytearray(
        protocol.generate_header(compression_type=protocol.NO_COMPRESSION)
    )
    frame.extend(event.to_bytes(4, "big"))
    if session_id:
        frame.extend(len(session_id).to_bytes(4, "big"))
        frame.extend(str.encode(session_id))
    frame.extend(len(payload_bytes).to_bytes(4, "big"))
    frame.extend(payload_bytes)
    return bytes(frame)


class VolcTtsClient:
    DEFAULT_SPEAKER = DEFAULT_VOLC_SPEAKER

    def __init__(self, app_id: str, access_key: str, session_id: str) -> None:
        self.app_id = app_id
        self.access_key = access_key
        self.session_id = session_id
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.logid = ""

    async def connect(self) -> None:
        headers = {
            "X-Api-App-Id": self.app_id,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": VOLC_TTS_RESOURCE_ID,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self.ws = await websockets.connect(
            VOLC_TTS_WS_URL,
            additional_headers=headers,
            ssl=ssl_ctx,
        )
        if self.ws and hasattr(self.ws, "response") and self.ws.response:
            self.logid = self.ws.response.headers.get("X-Tt-Logid", "")
        logger.info("[volc-tts] connected, logid: %s", self.logid)

        await self.ws.send(_frame(1, {}))
        resp = protocol.parse_response(await self.ws.recv())
        logger.debug("[volc-tts] StartConnection response: %s", resp)

    async def start_session(
        self,
        speaker: str,
        sample_rate: int = 24000,
        session_id: str | None = None,
        format: str = "mp3",
    ) -> None:
        if not self.ws:
            raise RuntimeError("VolcTtsClient not connected")
        sid = session_id or self.session_id
        payload = {
            "event": 100,
            "req_params": {
                "speaker": speaker,
                "audio_params": {"format": format, "sample_rate": sample_rate},
            },
        }
        await self.ws.send(_frame(100, payload, sid))
        resp = protocol.parse_response(await self.ws.recv())
        logger.info("[volc-tts] StartSession response: %s", resp)

    async def send_text(self, text: str, session_id: str | None = None) -> None:
        if not self.ws:
            raise RuntimeError("VolcTtsClient not connected")
        sid = session_id or self.session_id
        payload = {"event": 200, "req_params": {"text": text}}
        await self.ws.send(_frame(200, payload, sid))

    async def finish_session(self, session_id: str | None = None) -> None:
        if not self.ws:
            return
        sid = session_id or self.session_id
        payload = {"event": 102, "session_id": sid}
        await self.ws.send(_frame(102, payload, sid))

    async def receive_audio_stream(self, timeout: float = 30.0, session_id: str | None = None) -> AsyncIterator[bytes]:
        """逐帧产出 mp3 音频（event 352），直到会话结束（152），实现真流式播放。

        每帧到达即 yield，调用方可直接转发给播放端，无需等整段合成完。
        """
        if not self.ws:
            raise RuntimeError("VolcTtsClient not connected")
        _ = session_id
        async with asyncio.timeout(timeout):
            while True:
                resp = protocol.parse_response(await self.ws.recv())
                event = resp.get("event")
                if event == 352:
                    payload = resp.get("payload_msg")
                    if isinstance(payload, bytes):
                        yield payload
                    elif isinstance(payload, str):
                        yield payload.encode("utf-8")
                elif event == 152:
                    break
                elif event == 153:
                    raise RuntimeError(f"Volc TTS session failed: {resp}")
                elif event == 51:
                    raise RuntimeError(f"Volc TTS connection failed: {resp}")

    async def receive_audio(self, timeout: float = 30.0) -> bytes:
        """Collect mp3 audio frames until session finished. Returns mp3 bytes."""
        out = bytearray()
        async for chunk in self.receive_audio_stream(timeout=timeout):
            out.extend(chunk)
        return bytes(out)

    async def close(self) -> None:
        if not self.ws:
            return
        try:
            await self.ws.send(_frame(2, {}))
        except Exception:
            logger.debug("[volc-tts] close frame send failed", exc_info=True)
        await self.ws.close()
        self.ws = None
