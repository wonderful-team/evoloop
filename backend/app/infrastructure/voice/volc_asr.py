import gzip
import json
import logging
import ssl
import uuid
from typing import Any

import websockets

from app.infrastructure.voice import volc_protocol as protocol

logger = logging.getLogger(__name__)

VOLC_ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
VOLC_ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"
VOLC_ASR_MODEL = "bigmodel"


class VolcAsrClient:
    """Volcengine bigmodel 流式 ASR 客户端（文档 6561/1354869，双向流式优化版）。

    dictation 听写链路专用：按时长计费，避免占用对话大模型（token 计费）。
    事件映射兼容 voice_receive_loop：增量识别 → event 451，最终结果（负包响应）→ event 459。
    """

    def __init__(self, app_id: str, access_key: str) -> None:
        self.app_id = app_id
        self.access_key = access_key
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.logid = ""

    async def connect(self) -> None:
        """建立 WebSocket 连接并发送 Full Client Request（pcm 16k 单声道）。"""
        headers = {
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": VOLC_ASR_RESOURCE_ID,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        logger.info(f"Connecting to Volcengine ASR: {VOLC_ASR_WS_URL}")

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self.ws = await websockets.connect(
            VOLC_ASR_WS_URL,
            additional_headers=headers,
            ssl=ssl_ctx,
        )
        self.logid = ""
        if self.ws and hasattr(self.ws, "response") and self.ws.response:
            self.logid = self.ws.response.headers.get("X-Tt-Logid", "")
        logger.info(f"Connected to Volcengine ASR, logid: {self.logid}")

        payload = {
            "user": {"uid": "evo-loop-asr"},
            "audio": {"format": "pcm", "rate": 16000, "bits": 16, "channel": 1},
            "request": {
                "model_name": VOLC_ASR_MODEL,
                "enable_itn": True,
                "enable_ddc": True,
                "enable_punc": True,
            },
        }
        payload_bytes = gzip.compress(str.encode(json.dumps(payload)))
        req = bytearray(
            protocol.generate_header(
                message_type=protocol.CLIENT_FULL_REQUEST,
                message_type_specific_flags=protocol.NO_SEQUENCE,
            )
        )
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)
        logger.info("ASR full client request sent")

    async def send_audio(self, audio: bytes) -> None:
        """发送客户端麦克风 PCM 音频块（gzip 压缩）。"""
        if not self.ws:
            return
        payload_bytes = gzip.compress(audio)
        req = bytearray(
            protocol.generate_header(
                message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
                message_type_specific_flags=protocol.NO_SEQUENCE,
                serial_method=protocol.NO_SERIALIZATION,
            )
        )
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)

    async def finish(self) -> None:
        """发送最后一帧（负包），通知服务端音频流结束并返回最终结果。"""
        if not self.ws:
            return
        silence = b"\x00\x00" * 1600  # 50ms @16k/16bit
        payload_bytes = gzip.compress(silence)
        req = bytearray(
            protocol.generate_header(
                message_type=protocol.CLIENT_AUDIO_ONLY_REQUEST,
                message_type_specific_flags=protocol.NEG_SEQUENCE,
                serial_method=protocol.NO_SERIALIZATION,
            )
        )
        req.extend(len(payload_bytes).to_bytes(4, "big"))
        req.extend(payload_bytes)
        await self.ws.send(req)

    async def receive_response(self) -> dict[str, Any]:
        """接收并解析 ASR 响应，映射为 voice_receive_loop 兼容事件。

        - 增量识别文本 → SERVER_FULL_RESPONSE / event 451（payload 携带 origin_text）
        - 最终结果（负包响应）→ SERVER_FULL_RESPONSE / event 459
        - 错误帧 → SERVER_ERROR
        - 空文本等无意义包 → 内部继续等待下一个包
        """
        while self.ws:
            res = await self.ws.recv()
            parsed = self._parse_frame(res)
            if parsed is not None:
                return parsed
        raise RuntimeError("WebSocket not connected")

    def _parse_frame(self, res: bytes | str) -> dict[str, Any] | None:
        if isinstance(res, str):
            res = res.encode("utf-8")
        if len(res) < 4:
            return None
        header_size = res[0] & 0x0F
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0F
        message_compression = res[2] & 0x0F
        payload = res[header_size * 4 :]

        if message_type == protocol.SERVER_ERROR_RESPONSE:
            payload_msg = payload[8:]
            if message_compression == protocol.GZIP:
                try:
                    payload_msg = gzip.decompress(payload_msg)
                except (OSError, ValueError):
                    logger.warning(
                        "[asr] error payload gzip decompress failed",
                        exc_info=True,
                    )
            try:
                payload_msg = json.loads(payload_msg.decode("utf-8"))
            except (OSError, ValueError):
                logger.warning(
                    "[asr] error payload JSON decode failed", exc_info=True
                )
            logger.error("[asr] server error: %s", str(payload_msg)[:300])
            return {"message_type": "SERVER_ERROR", "payload_msg": payload_msg}

        if message_type != protocol.SERVER_FULL_RESPONSE:
            return None

        start = 0
        parsed_event: int | None = None
        if message_type_specific_flags & protocol.POS_SEQUENCE:
            start += 4  # sequence number
        if message_type_specific_flags & protocol.MSG_WITH_EVENT:
            # Event-carrying frames put the event code in the first 4 payload
            # bytes (e.g. control events). Recognized events are 451 (partial)
            # and 459 (final); anything else is forwarded as-is.
            if len(payload) < start + 4:
                return None
            parsed_event = int.from_bytes(
                payload[start : start + 4], "big", signed=False
            )
            start += 4
        payload = payload[start:]
        if len(payload) < 4:
            return None
        payload_size = int.from_bytes(payload[:4], "big", signed=False)
        payload_msg = payload[4 : 4 + payload_size]
        if message_compression == protocol.GZIP:
            try:
                payload_msg = gzip.decompress(payload_msg)
            except Exception:
                return None
        try:
            data = json.loads(payload_msg.decode("utf-8"))
        except Exception:
            return None

        text = ((data.get("result") or {}).get("text") or "").strip()
        if not text:
            # Empty-text frames carry no recognition result (control/event
            # frames). voice_receive_loop only consumes 451/459 with text.
            return None

        is_final = bool(message_type_specific_flags & protocol.NEG_SEQUENCE)
        event = 459 if is_final else (parsed_event or 451)
        return {
            "message_type": "SERVER_FULL_RESPONSE",
            "event": event,
            "payload_msg": {"extra": {"origin_text": text}},
        }

    async def close(self) -> None:
        """关闭 WebSocket 连接。"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                logger.debug("[asr] ws.close failed", exc_info=True)
            self.ws = None
