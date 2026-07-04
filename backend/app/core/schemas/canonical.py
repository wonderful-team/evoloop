"""EvoLoop Canonical Message Schema — Python Pydantic Models
Source: schemas/message.json (JSON Schema)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


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


class EndpointKind(str, Enum):
    MOBILE = "mobile"
    AGENT = "agent"
    GATEWAY = "gateway"
    BACKEND = "backend"
    MC = "mc"


# ============ Envelope ============

class Endpoint(BaseModel):
    kind: EndpointKind | str
    device_key: Optional[str] = None


class Envelope(BaseModel):
    version: str = "2.0"
    type: MessageType | str
    message_id: str
    timestamp: int  # unix ms
    source: Optional[Endpoint] = None
    target: Optional[Endpoint] = None
    body: dict[str, Any]


# ============ command.relay ============

class CommandRelayBody(BaseModel):
    command_id: Optional[int] = None
    message_id: str
    thread_id: str
    project_id: Optional[int] = None
    action: str
    content: dict[str, Any]
    references: Optional[List[dict[str, Any]]] = None


# ============ command.ack ============

class CommandAckBody(BaseModel):
    command_id: int
    thread_id: Optional[str] = None
    status: str  # received | completed | failed | timed_out
    error: Optional[str] = None


# ============ command.stop / retry / rewind ============

class CommandStopBody(BaseModel):
    command_id: Optional[int] = None
    thread_id: str


class CommandRetryBody(BaseModel):
    command_id: Optional[int] = None
    thread_id: str
    message_id: Optional[str] = None
    revert_files: Optional[bool] = None


class CommandRewindBody(BaseModel):
    command_id: Optional[int] = None
    thread_id: str
    message_id: Optional[str] = None
    revert_files: Optional[bool] = None


# ============ hitl ============

class HITLRequestBody(BaseModel):
    request_id: str
    request_type: str  # confirmation | choice | text | approval | project_switch | file_select
    prompt: str
    options: Optional[List[str]] = None
    context: Optional[str] = None
    default_value: Optional[str] = None
    tool_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class HITLResponseBody(BaseModel):
    command_id: Optional[int] = None
    request_id: str
    action: str  # confirm | choice | text
    value: str


class HITLCancelBody(BaseModel):
    command_id: Optional[int] = None
    request_id: str
    thread_id: Optional[str] = None


# ============ message.sync ============

class SyncMessage(BaseModel):
    message_id: str
    thread_id: str
    role: str  # human | ai | tool | system
    content_type: Optional[str] = None  # text | markdown | json | multipart
    content: str
    created_at: int  # unix timestamp (seconds)
    sequence_number: Optional[int] = None
    status: Optional[str] = None
    action_type: Optional[str] = None
    parent_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    thinking: Optional[str] = None
    checkpoint_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    category: Optional[str] = None
    node_source: Optional[str] = None
    source: Optional[str] = None
    is_visible: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = None


class MessageSyncBody(BaseModel):
    thread_id: str
    sync_mode: str  # full | incremental
    device_key: str
    messages: list[SyncMessage]
    conversation: Optional[dict[str, Any]] = None


# ============ message.deleted ============

class MessageDeletedBody(BaseModel):
    thread_id: str
    message_ids: list[str]


# ============ device.status ============

class DeviceStatusBody(BaseModel):
    device_key: str
    online: bool
    client_id: Optional[str] = None


# ============ device.heartbeat ============

class DeviceHeartbeatBody(BaseModel):
    timestamp: int


# ============ agent.status ============

class AgentStatusBody(BaseModel):
    command_id: Optional[int] = None
    thread_id: Optional[str] = None
    status: str
    error: Optional[str] = None


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
    message_id: Optional[str] = None,
    source: Optional[Endpoint] = None,
    target: Optional[Endpoint] = None,
) -> Envelope:
    """Factory: build a canonical Envelope with auto-generated message_id.
    Timestamp is Unix seconds, matching Go's time.Now().Unix().
    """
    import uuid, time
    return Envelope(
        version="2.0",
        type=type,
        message_id=message_id or str(uuid.uuid4()),
        timestamp=int(time.time()),  # seconds (not ms)
        source=source,
        target=target,
        body=body,
    )


def is_canonical_envelope(data: dict) -> bool:
    """Check if a dict is a canonical envelope (has version='2.0' + message_id)."""
    return isinstance(data, dict) and data.get("version") == "2.0" and isinstance(data.get("message_id"), str)
