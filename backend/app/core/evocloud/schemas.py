from typing import Any

from pydantic import BaseModel, ConfigDict

from app.utils.model_helpers import LegacyDictMixin


class EvoCloudConfig(BaseModel):
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


class EvoCloudAttachment(BaseModel, LegacyDictMixin):
    """Attachment metadata in an EvoCloud command."""
    model_config = ConfigDict(extra="allow")


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


class DeviceStatus(BaseModel):
    """Current status of the device connection."""

    is_logged_in: bool
    member_id: int | None = None
    device_connected: bool
    device_id: int | None = None
    device_name: str | None = None


class SyncConversation(BaseModel, LegacyDictMixin):
    id: str
    project_id: int = 0
    title: str = "新会话"
    created_at: int
    updated_at: int


class SyncMessage(BaseModel, LegacyDictMixin):
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


class RemoteCommand(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    command_id: str | int | None = None
    type: str = "chat_message"
    content: dict[str, Any] | None = None
    message: str | None = None
    attachments: list[EvoCloudAttachment] = []
    thread_id: str | None = None
    project_id: int | None = None


class ProjectSwitchEvent(BaseModel, LegacyDictMixin):
    project_id: int | None = None
    project_name: str | None = None
    external_path: str | None = None
    path: str | None = None


class QueryResponseData(BaseModel, LegacyDictMixin):
    """Payload for a query response."""
    model_config = ConfigDict(extra="allow")


class QueryResponse(BaseModel, LegacyDictMixin):
    type: str = "query_response"
    request_id: str | int | None = None
    data: QueryResponseData


class HandshakePayload(BaseModel, LegacyDictMixin):
    """Payload for the EvoCloud WebSocket handshake."""
    model_config = ConfigDict(extra="allow")


class WebSocketHandshake(BaseModel, LegacyDictMixin):
    type: str = "connect"
    payload: HandshakePayload


class WebSocketPing(BaseModel, LegacyDictMixin):
    type: str = "ping"
    timestamp: int


class ToolLogState(BaseModel, LegacyDictMixin):
    content: str | None = None
    timestamp: float = 0.0
    name: str | None = None


class ThoughtLogState(BaseModel, LegacyDictMixin):
    content: str | None = None
    timestamp: float = 0.0


class ConversationQueryItem(BaseModel, LegacyDictMixin):
    id: str
    title: str
    project_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MessageQueryItem(BaseModel, LegacyDictMixin):
    id: str
    role: str
    content: str | None = None
    created_at: str | None = None


class McpServerInfo(BaseModel, LegacyDictMixin):
    name: str
    type: str
    connected: bool


class ModelInfo(BaseModel, LegacyDictMixin):
    id: str
    name: str
