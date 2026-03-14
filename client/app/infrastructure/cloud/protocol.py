"""
Client-Server Protocol Definitions for EvoLoop CS Architecture.

Defines message formats, error codes, and communication patterns
between EvoLoop Client devices and EvoLoop Cloud.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Literal
import json


class MessageType(Enum):
    """Message types for WebSocket communication."""

    # Client -> Server
    HEARTBEAT = "heartbeat"
    REGISTER = "register"
    AGENT_REQUEST = "agent_request"
    MEMORY_QUERY = "memory_query"
    SKILL_DOWNLOAD = "skill_download"
    EXECUTION_REPORT = "execution_report"

    # Server -> Client
    HEARTBEAT_ACK = "heartbeat_ack"
    REGISTER_ACK = "register_ack"
    AGENT_RESPONSE = "agent_response"
    MEMORY_RESULT = "memory_result"
    SKILL_PACKAGE = "skill_package"
    NOTIFICATION = "notification"

    # Bidirectional
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class ErrorCode(IntEnum):
    """Standard error codes for Cloud API responses."""

    # Success
    SUCCESS = 0

    # Authentication (1xx)
    AUTH_INVALID_TOKEN = 101
    AUTH_TOKEN_EXPIRED = 102
    AUTH_DEVICE_NOT_REGISTERED = 103
    AUTH_RATE_LIMITED = 104

    # Request Errors (2xx)
    REQUEST_INVALID = 201
    REQUEST_MISSING_FIELD = 202
    REQUEST_TOO_LARGE = 203
    REQUEST_TIMEOUT = 204

    # Resource Errors (3xx)
    RESOURCE_NOT_FOUND = 301
    RESOURCE_UNAVAILABLE = 302
    RESOURCE_RATE_LIMITED = 303

    # Server Errors (4xx)
    SERVER_INTERNAL_ERROR = 401
    SERVER_MAINTENANCE = 402
    SERVER_OVERLOADED = 403

    # Network Errors (5xx)
    NETWORK_UNREACHABLE = 501
    NETWORK_TIMEOUT = 502

    # Service Disabled (6xx - Client mode)
    SERVICE_DISABLED = 601
    CLOUD_NOT_CONFIGURED = 602


@dataclass
class CloudMessage:
    """
    Standard message format for WebSocket communication.

    All messages follow this structure for consistency.
    """

    # Required fields
    msg_type: MessageType
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f"))

    # Optional fields
    device_id: str | None = None
    session_id: str | None = None

    # Payload
    payload: dict[str, Any] = field(default_factory=dict)

    # Error information
    error_code: ErrorCode | None = None
    error_message: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "msg_type": self.msg_type.value,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "device_id": self.device_id,
            "session_id": self.session_id,
            "payload": self.payload,
        }
        if self.error_code is not None:
            data["error_code"] = self.error_code.value
            data["error_message"] = self.error_message
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "CloudMessage":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            msg_type=MessageType(data["msg_type"]),
            timestamp=data["timestamp"],
            message_id=data["message_id"],
            device_id=data.get("device_id"),
            session_id=data.get("session_id"),
            payload=data.get("payload", {}),
            error_code=ErrorCode(data["error_code"]) if "error_code" in data else None,
            error_message=data.get("error_message"),
        )

    @classmethod
    def heartbeat(cls, device_id: str, status: str = "online") -> "CloudMessage":
        """Create heartbeat message."""
        return cls(
            msg_type=MessageType.HEARTBEAT,
            device_id=device_id,
            payload={"status": status, "timestamp": datetime.utcnow().isoformat()}
        )

    @classmethod
    def agent_request(
        cls,
        device_id: str,
        session_id: str,
        intent: str,
        context: dict | None = None
    ) -> "CloudMessage":
        """Create agent request message."""
        return cls(
            msg_type=MessageType.AGENT_REQUEST,
            device_id=device_id,
            session_id=session_id,
            payload={
                "intent": intent,
                "context": context or {},
                "local_state": {},
                "request_type": "plan"
            }
        )

    @classmethod
    def error(
        cls,
        error_code: ErrorCode,
        error_message: str,
        device_id: str | None = None
    ) -> "CloudMessage":
        """Create error message."""
        return cls(
            msg_type=MessageType.ERROR,
            device_id=device_id,
            error_code=error_code,
            error_message=error_message
        )


@dataclass
class AgentRequest:
    """Agent request payload structure."""
    intent: str
    context: dict[str, Any]
    local_state: dict[str, Any]
    request_type: Literal["plan", "decide", "reflect"] = "plan"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "context": self.context,
            "local_state": self.local_state,
            "request_type": self.request_type,
        }


@dataclass
class AgentResponse:
    """Agent response payload structure."""
    decision: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    reasoning: str | None
    ltm_context: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict) -> "AgentResponse":
        return cls(
            decision=data.get("decision", {}),
            tool_calls=data.get("tool_calls", []),
            reasoning=data.get("reasoning"),
            ltm_context=data.get("ltm_context", {}),
        )


@dataclass
class MemoryRecallRequest:
    """Memory recall request payload."""
    query: str
    memory_types: list[str]
    limit: int = 10
    recency_weight: float = 0.3

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "memory_types": self.memory_types,
            "limit": self.limit,
            "recency_weight": self.recency_weight,
        }


@dataclass
class MemoryRecallResponse:
    """Memory recall response payload."""
    memories: list[dict[str, Any]]
    total_available: int
    query_embedding: list[float] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecallResponse":
        return cls(
            memories=data.get("memories", []),
            total_available=data.get("total_available", 0),
            query_embedding=data.get("query_embedding"),
        )


@dataclass
class SkillDownloadRequest:
    """Skill download request payload."""
    skill_id: str
    include_atlas: bool = True
    include_macro: bool = True

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "include_atlas": self.include_atlas,
            "include_macro": self.include_macro,
        }


@dataclass
class SkillPackage:
    """Complete skill package structure."""
    skill_id: str
    name: str
    version: str
    platform: str
    macro: dict[str, Any]
    atlas_snapshot: dict[str, Any]
    description: dict[str, Any]
    verification_status: str
    success_rate: float
    execution_count: int
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "SkillPackage":
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            version=data["version"],
            platform=data["platform"],
            macro=data["macro"],
            atlas_snapshot=data["atlas_snapshot"],
            description=data["description"],
            verification_status=data["verification_status"],
            success_rate=data["success_rate"],
            execution_count=data.get("execution_count", 0),
            created_at=data["created_at"],
        )


@dataclass
class DeviceRegistration:
    """Device registration payload."""
    device_name: str
    platform: str  # windows, macos, linux
    version: str
    hardware_id: str
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "device_name": self.device_name,
            "platform": self.platform,
            "version": self.version,
            "hardware_id": self.hardware_id,
            "capabilities": self.capabilities,
        }


@dataclass
class DeviceCredentials:
    """Device credentials returned after registration."""
    device_id: str
    access_token: str
    refresh_token: str
    expires_in: int

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceCredentials":
        return cls(
            device_id=data["device_id"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data["expires_in"],
        )


# Error message mapping for user-friendly display
ERROR_MESSAGES = {
    ErrorCode.AUTH_INVALID_TOKEN: "Invalid device token. Please re-register.",
    ErrorCode.AUTH_TOKEN_EXPIRED: "Session expired. Refreshing...",
    ErrorCode.AUTH_DEVICE_NOT_REGISTERED: "Device not registered. Please register first.",
    ErrorCode.AUTH_RATE_LIMITED: "Too many requests. Please wait.",
    ErrorCode.REQUEST_INVALID: "Invalid request format.",
    ErrorCode.REQUEST_TIMEOUT: "Request timed out. Retrying...",
    ErrorCode.RESOURCE_NOT_FOUND: "Requested resource not found.",
    ErrorCode.SERVER_INTERNAL_ERROR: "Server error. Please try again later.",
    ErrorCode.SERVER_MAINTENANCE: "Server under maintenance.",
    ErrorCode.NETWORK_UNREACHABLE: "Cannot reach EvoLoop Cloud.",
    ErrorCode.NETWORK_TIMEOUT: "Network timeout. Check your connection.",
    ErrorCode.SERVICE_DISABLED: "Cloud service disabled in client mode.",
    ErrorCode.CLOUD_NOT_CONFIGURED: "Cloud URL not configured.",
}


def get_error_message(error_code: ErrorCode) -> str:
    """Get user-friendly error message for error code."""
    return ERROR_MESSAGES.get(error_code, f"Unknown error: {error_code}")
