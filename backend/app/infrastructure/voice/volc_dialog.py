import gzip
import json
import uuid
import logging
from typing import Dict, Any, Optional
import websockets

from app.infrastructure.voice import volc_protocol as protocol

logger = logging.getLogger(__name__)


class VolcDialogClient:
    def __init__(self, app_id: str, access_key: str, session_id: str) -> None:
        self.app_id = app_id
        self.access_key = access_key
        self.session_id = session_id
        self.base_url = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.logid = ""

    async def connect(self) -> None:
        """Establish WebSocket connection to Volcengine."""
        headers = {
            "X-Api-App-ID": self.app_id,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": "volc.speech.dialog",
            "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        logger.info(f"Connecting to Volcengine Realtime Dialogue: {self.base_url}")

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self.ws = await websockets.connect(
            self.base_url,
            additional_headers=headers,
            ssl=ssl_ctx,
        )
        self.logid = ""
        if self.ws and hasattr(self.ws, "response") and self.ws.response:
            self.logid = self.ws.response.headers.get("X-Tt-Logid", "")
        logger.info(f"Connected to Volcengine, logid: {self.logid}")

        # Send StartConnection request
        start_conn = bytearray(protocol.generate_header())
        start_conn.extend(int(1).to_bytes(4, 'big'))
        payload_bytes = gzip.compress(str.encode("{}"))
        start_conn.extend(len(payload_bytes).to_bytes(4, 'big'))
        start_conn.extend(payload_bytes)
        await self.ws.send(start_conn)

        response = await self.ws.recv()
        logger.debug(f"StartConnection response: {protocol.parse_response(response)}")

        # Send StartSession request
        request_params = {
            "asr": {
                "extra": {
                    "end_smooth_window_ms": 1500,
                },
            },
            "dialog": {
                "bot_name": "EvoLoop",
                "system_role": "你是一个智能语音助手，名叫EvoLoop。请用自然、简洁的方式回答用户的问题。",
                "speaking_style": "你说话自然亲切，语气友好。",
                "dialog_id": "",
                "extra": {
                    "strict_audit": False,
                    "recv_timeout": 60,
                    "input_mod": "audio",
                }
            },
            "tts": {
                "audio_config": {
                    "channel": 1,
                    "format": "pcm",
                    "sample_rate": 24000
                }
            },
        }
        payload_bytes = gzip.compress(str.encode(json.dumps(request_params)))
        start_session = bytearray(protocol.generate_header())
        start_session.extend((100).to_bytes(4, "big"))
        start_session.extend(len(self.session_id).to_bytes(4, "big"))
        start_session.extend(str.encode(self.session_id))
        start_session.extend(len(payload_bytes).to_bytes(4, "big"))
        start_session.extend(payload_bytes)
        await self.ws.send(start_session)

        response = await self.ws.recv()
        logger.debug(f"StartSession response: {protocol.parse_response(response)}")

    async def send_audio(self, audio: bytes) -> None:
        """Send client mic PCM audio block."""
        if not self.ws:
            return
        task_req = bytearray(
            protocol.generate_header(
                message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
                serial_method=protocol.NO_SERIALIZATION,
            )
        )
        task_req.extend((200).to_bytes(4, "big"))
        task_req.extend(len(self.session_id).to_bytes(4, "big"))
        task_req.extend(str.encode(self.session_id))
        payload_bytes = gzip.compress(audio)
        task_req.extend(len(payload_bytes).to_bytes(4, "big"))
        task_req.extend(payload_bytes)
        await self.ws.send(task_req)

    async def send_chat_text_query(self, content: str) -> None:
        """Send Chat Text Query (used to inject text response or trigger direct query)."""
        if not self.ws:
            return
        payload = {"content": content}
        payload_bytes = gzip.compress(str.encode(json.dumps(payload)))

        req = bytearray(protocol.generate_header())
        req.extend((501).to_bytes(4, "big"))
        req.extend(len(self.session_id).to_bytes(4, "big"))
        req.extend(str.encode(self.session_id))
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)

    async def send_chat_tts_text(self, start: bool, end: bool, content: str) -> None:
        """Send Chat TTS Text to synthesize text to audio."""
        if not self.ws:
            return
        logger.debug(f"Sending ChatTTSText start={start} end={end} len={len(content)}")
        payload = {
            "start": start,
            "end": end,
            "content": content,
        }
        payload_bytes = gzip.compress(str.encode(json.dumps(payload)))

        req = bytearray(protocol.generate_header())
        req.extend((500).to_bytes(4, "big"))
        req.extend(len(self.session_id).to_bytes(4, "big"))
        req.extend(str.encode(self.session_id))
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)

    async def finish_session(self) -> None:
        """Send FinishSession command."""
        if not self.ws:
            return
        req = bytearray(protocol.generate_header())
        req.extend((102).to_bytes(4, "big"))
        payload_bytes = gzip.compress(str.encode("{}"))
        req.extend(len(self.session_id).to_bytes(4, "big"))
        req.extend(str.encode(self.session_id))
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)

    async def receive_response(self) -> Dict[str, Any]:
        """Receive message from Volcengine and parse it."""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        response = await self.ws.recv()
        return protocol.parse_response(response)

    async def close(self) -> None:
        """Close WebSocket connection."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def reconnect(self) -> None:
        """Reconnect to Volcengine (for session timeout recovery)."""
        await self.close()
        await self.connect()
