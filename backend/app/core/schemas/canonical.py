"""EvoLoop Canonical Message Schema — Python Pydantic Models
Source: schemas/message.json (JSON Schema)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

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
    MESSAGE_DELETED = "message.deleted"
    DEVICE_STATUS = "device.status"
    DEVICE_HEARTBEAT = "device.heartbeat"
    AGENT_STATUS = "agent.status"
    SYSTEM_INIT = "system.init"
    SYSTEM_ERROR = "system.error"
    MEMORY_SYNC = "memory.sync"
    # Voice assistant (thin-client) channel
    VOICE_ROUTE = "voice.route"
    VOICE_CANCEL = "voice.cancel"
    VOICE_ROUTE_RESULT = "voice.route_result"
    # Full-duplex streaming extensions
    VOICE_PARTIAL = "voice.partial"
    VOICE_BARGE_IN = "voice.barge_in"
    VOICE_TOKEN = "voice.token"
    VOICE_TTS_BOUNDARY = "voice.tts_boundary"
    VOICE_DICTATION_FINALIZE = "voice.dictation.finalize"
    VOICE_DICTATION_POLISHED = "voice.dictation.polished"


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

class CommandRelayContent(BaseModel):
    text: str | None = None
    references: list[Attachment] | None = None


class CommandRelayBody(BaseModel):
    command_id: int | None = None
    message_id: str
    thread_id: str
    project_id: int | None = None
    action: str
    content: str | CommandRelayContent
    references: Optional[List[dict[str, Any]]] = None


# ============ command.ack ============

class CommandAckBody(BaseModel):
    command_id: int
    thread_id: str | None = None
    status: str  # received | completed | failed | timed_out
    error: str | None = None


# ============ command.stop / retry / rewind ============

class CommandStopBody(BaseModel):
    command_id: int | None = None
    thread_id: str


class CommandRetryBody(BaseModel):
    command_id: int | None = None
    thread_id: str
    message_id: str | None = None
    revert_files: bool | None = None


class CommandRewindBody(BaseModel):
    command_id: int | None = None
    thread_id: str
    message_id: str | None = None
    revert_files: bool | None = None


# ============ hitl ============

class HITLRequestBody(BaseModel):
    request_id: str
    request_type: str  # confirmation | choice | text | approval | project_switch | file_select
    prompt: str
    options: List[str] | None = None
    context: str | None = None
    default_value: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] | None = None


class HITLResponseBody(BaseModel):
    command_id: int | None = None
    request_id: str
    action: str  # confirm | choice | text
    value: str


class HITLCancelBody(BaseModel):
    command_id: int | None = None
    request_id: str
    thread_id: str | None = None


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
    tool_calls: Optional[list[dict[str, Any]]] = None
    category: str | None = None
    node_source: str | None = None
    source: str | None = None
    is_visible: bool | None = None
    metadata: dict[str, Any] | None = None


class MessageSyncBody(BaseModel):
    thread_id: str
    sync_mode: str  # full | incremental
    device_key: str
    messages: list[SyncMessage]
    conversation: dict[str, Any] | None = None


# ============ message.deleted ============

class MessageDeletedBody(BaseModel):
    thread_id: str
    message_ids: list[str]


# ============ device.status ============

class DeviceStatusBody(BaseModel):
    device_key: str
    online: bool
    client_id: str | None = None


# ============ device.heartbeat ============

class DeviceHeartbeatBody(BaseModel):
    timestamp: int


# ============ agent.status ============

class AgentStatusBody(BaseModel):
    command_id: int | None = None
    thread_id: str | None = None
    status: str
    error: str | None = None


# ============ system ============

class SystemInitBody(BaseModel):
    client_id: str
    device_key: str


class SystemErrorBody(BaseModel):
    code: str
    message: str


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
    return isinstance(data, dict) and data.get("version") == "2.0" and isinstance(data.get("message_id"), str)
