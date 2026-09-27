"""EvoLoop Canonical Message Schema — Python Pydantic Models
Source: schemas/message.json (JSON Schema)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.utils.id import gen_uuid

# ============ Enums ============


class MessageType(str, Enum):
    COMMAND_RELAY = "command.relay"
    COMMAND_ACK = "command.ack"
    COMMAND_STOP = "command.stop"
    COMMAND_RETRY = "command.retry"
    COMMAND_REWIND = "command.rewind"
    HITL_REQUEST = "hitl.request"
    HITL_RESPONSE = "hitl.response"
    HITL_CANCEL = "hitl.cancel"
    MESSAGE_SYNC = "message.sync"
    AGENT_STATUS = "agent.status"
    SYSTEM_INIT = "system.init"
    SYSTEM_ERROR = "system.error"
    MEMORY_SYNC = "memory.sync"
    # Voice assistant (thin-client) channel
    VOICE_START = "voice.start"
    VOICE_STOP = "voice.stop"
    VOICE_ROUTE = "voice.route"
    VOICE_CANCEL = "voice.cancel"
    VOICE_ROUTE_RESULT = "voice.route_result"
    # Full-duplex streaming extensions
    VOICE_PARTIAL = "voice.partial"
    VOICE_BARGE_IN = "voice.barge_in"
    VOICE_TOKEN = "voice.token"
    VOICE_TTS_BOUNDARY = "voice.tts_boundary"
    VOICE_TTS_PLAY = "voice.tts_play"
    VOICE_DICTATION_FINALIZE = "voice.dictation.finalize"
    VOICE_DICTATION_POLISHED = "voice.dictation.polished"
    VOICE_STATE = "voice.state"
    VOICE_NAVIGATE = "voice.navigate"
    DICTATION_PASTE = "dictation.paste"
    SYSTEM_STATE_CHANGED = "system.state_changed"
    SYSTEM_CONFIG_CHANGED = "system.config_changed"


class EndpointKind(str, Enum):
    MOBILE = "mobile"
    AGENT = "agent"
    GATEWAY = "gateway"
    BACKEND = "backend"
    MC = "mc"
    VOICE = "voice"


# ============ Envelope ============


class Endpoint(BaseModel):
    kind: EndpointKind | str
    device_key: str | None = None


class AttachmentType(str, Enum):
    FILE = "file"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    MESSAGE = "message"
    ARTIFACT = "artifact"
    CHANGESET = "changeset"
    SKILL = "skill"
    DIRECTORY = "directory"


class Attachment(BaseModel):
    id: str
    type: AttachmentType | str
    target_id: str
    target_name: str
    meta_data: dict[str, Any] | None = None


class Envelope(BaseModel):
    version: str = "2.0"
    type: MessageType | str
    message_id: str
    timestamp: int  # unix seconds
    source: Endpoint | None = None
    target: Endpoint | None = None
    body: dict[str, Any]


# ============ command.relay ============


# ============ command.ack ============


# ============ command.stop / retry / rewind ============


# ============ hitl ============


# ============ message.sync ============


class SyncMessage(BaseModel):
    message_id: str
    thread_id: str
    role: str  # human | ai | tool | system
    content_type: str | None = None  # text | markdown | json | multipart
    content: str | dict[str, Any]
    references: list[Attachment] | None = None
    created_at: int  # unix timestamp (seconds)
    sequence_number: int | None = None
    status: str | None = None
    action_type: str | None = None
    parent_id: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    thinking: str | None = None
    checkpoint_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    category: str | None = None
    source: str | None = None
    is_visible: bool | None = None
    metadata: dict[str, Any] | None = None


# ============ agent.status ============


# ============ system ============


# ============ Helpers ============


def create_envelope(
    type: MessageType | str,
    body: dict[str, Any],
    *,
    message_id: str | None = None,
    source: Endpoint | None = None,
    target: Endpoint | None = None,
) -> Envelope:
    """Factory: build a canonical Envelope with auto-generated message_id.
    Timestamp is Unix seconds, matching Go's time.Now().Unix().
    """
    import time

    return Envelope(
        version="2.0",
        type=type,
        message_id=message_id or gen_uuid(),
        timestamp=int(time.time()),  # seconds (not ms)
        source=source,
        target=target,
        body=body,
    )


def is_canonical_envelope(data: dict) -> bool:
    """Check if a dict is a canonical envelope (has version='2.0' + message_id)."""
    return (
        isinstance(data, dict)
        and data.get("version") == "2.0"
        and isinstance(data.get("message_id"), str)
    )
