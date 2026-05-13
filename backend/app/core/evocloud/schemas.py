from typing import Any

from pydantic import field_validator

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
    parent_id: int | str = 0
    category: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    meta_data: Any | None = None
    content_type: str = "text"


class RemoteCommand(DynamicBaseModel):
    command_id: str | int | None = None
    type: str = "chat_message"        # 旧版指令类型
    action: str | None = None         # EPv2 指令动作 (chat/project_switch等)
    content: dict[str, Any] | None = None # 旧版负载
    payload: dict[str, Any] | None = None # EPv2 负载
    message: str | None = None
    attachments: list[dict[str, Any]] = []
    thread_id: str | None = None
    project_id: int | None = None

    def get_action(self) -> str:
        """获取标准化的指令动作名称"""
        return self.action or self.type or "chat_message"

    def get_payload(self) -> dict[str, Any]:
        """获取标准化的业务数据负载"""
        return self.payload or self.content or {}


class QueryResponse(DynamicBaseModel):
    type: str = "query_response"
    request_id: str | int | None = None
    data: dict[str, Any]


class WebSocketHandshake(DynamicBaseModel):
    type: str = "connect"
    payload: dict[str, Any]


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
    title: str = "新会话"
    project_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, v):
        if v is None:
            return "新会话"
        return str(v)


class MessageQueryItem(DynamicBaseModel):
    id: str
    role: str
    content: str | None = None
    thinking: str | None = None
    created_at: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, v):
        return str(v) if v is not None else ""


class McpServerInfo(DynamicBaseModel):
    name: str
    type: str
    connected: bool


class ModelInfo(DynamicBaseModel):
    id: str
    name: str

    @field_validator("id", "name", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""


class SkillQueryItem(DynamicBaseModel):
    id: int
    name: str
    namespace: str
    description: str


class EvoCloudProjectSummary(DynamicBaseModel):
    id: int | None = None
    name: str
    description: str = ""
    path: str = ""
    exists_locally: bool = False
    status_text: str = ""
    owner: str = ""
