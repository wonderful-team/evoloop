from typing import Any

from pydantic import BaseModel

from app.infrastructure.pydantic_base import DynamicBaseModel


class EvoCloudConfig(DynamicBaseModel):
    """Configuration for EvoCloud connectivity."""

    api_url: str
    ws_url: str
    api_key: str | None = None
    api_secret: str | None = None

    # Device Identity
    device_name: str | None = "EvoLoop-Desktop"

    # Auth (Optional, can be passed dynamically)
    access_token: str | None = None

    # Path Configuration
    app_data_dir: str | None = None

    # SSL Configuration (for development)
    ssl_verify: bool = True


class EvoCloudAttachment(DynamicBaseModel):
    """Attachment metadata in an EvoCloud command."""


class CommandData(BaseModel):
    """Structure of a command received from Cloud."""

    command_id: str
    type: str # 'chat_message', 'hitl_response', etc.
    content: dict[str, Any] | None = None
    # Flat structure support
    message: str | None = None
    attachments: list[EvoCloudAttachment] = []
    thread_id: str | None = None
    project_id: int | None = None


class SyncConversation(DynamicBaseModel):
    id: str
    project_id: int = 0
    title: str = "新会话"
    created_at: int
    updated_at: int


class SyncMessage(DynamicBaseModel):
    id: str | int
    thread_id: str
    project_id: int = 0
    role: str
    content: str | None = None
    thinking: str | None = None
    created_at: int
    sequence_number: int = 0
    checkpoint_id: str = ""
    tool_calls: Any | None = None
    action_type: str = "text"
    is_visible: int = 1
    run_id: str = ""
    status: str = "completed"
    steps_snapshot: Any | None = None
    parent_id: int | str = 0
    category: str = ""


class RemoteCommand(DynamicBaseModel):
    command_id: str | int | None = None
    type: str = "chat_message"
    content: dict[str, Any] | None = None
    message: str | None = None
    attachments: list[EvoCloudAttachment] = []
    thread_id: str | None = None
    project_id: int | None = None


class QueryResponseData(DynamicBaseModel):
    """Payload for a query response."""


class QueryResponse(DynamicBaseModel):
    type: str = "query_response"
    request_id: str | int | None = None
    data: QueryResponseData


class HandshakePayload(DynamicBaseModel):
    """Payload for the EvoCloud WebSocket handshake."""


class WebSocketHandshake(DynamicBaseModel):
    type: str = "connect"
    payload: HandshakePayload


class WebSocketPing(DynamicBaseModel):
    type: str = "ping"
    timestamp: int


class ToolLogState(DynamicBaseModel):
    content: str | None = None
    timestamp: float = 0.0
    name: str | None = None


class ThoughtLogState(DynamicBaseModel):
    content: str | None = None
    timestamp: float = 0.0


class ConversationQueryItem(DynamicBaseModel):
    id: str
    title: str
    project_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MessageQueryItem(DynamicBaseModel):
    id: str
    role: str
    content: str | None = None
    created_at: str | None = None


class McpServerInfo(DynamicBaseModel):
    name: str
    type: str
    connected: bool


class ModelInfo(DynamicBaseModel):
    id: str
    name: str
