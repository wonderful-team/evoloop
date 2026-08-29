from typing import Any

from app.constants import DEFAULT_PROJECT_ID
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
    project_id: int = DEFAULT_PROJECT_ID
    title: str = "新会话"
    created_at: int
    updated_at: int
    is_pinned: bool = False


class SyncMessage(DynamicBaseModel):
    id: str | int
    thread_id: str
    project_id: int = DEFAULT_PROJECT_ID
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
    command_id: int | None = None
    action: str = "chat"
    content: dict[str, Any] | str | None = None
    message: str | None = None
    references: list[dict[str, Any]] = []
    thread_id: str | None = None
    project_id: int | None = None

    def get_action(self) -> str:
        """获取标准化的指令动作名称"""
        return self.action

    def get_payload(self) -> dict[str, Any]:
        """获取标准化的业务数据负载"""
        raw_payload = self.content or {}
        if isinstance(raw_payload, str):
            return {"text": raw_payload}
        return raw_payload


class EvoCloudProjectSummary(DynamicBaseModel):
    id: int | None = None
    name: str
    description: str = ""
    path: str = ""
    exists_locally: bool = False
    status_text: str = ""
    owner: str = ""


class TaskAttachment(DynamicBaseModel):
    """A2A 任务附带的文件中转描述"""

    filename: str
    download_url: str
    file_size: int
    md5: str


class AgentTask(DynamicBaseModel):
    """A2A 任务信封 - 在 RemoteCommand.content 中传输"""

    task_id: str
    task_type: str = "a2a_task"
    instruction: str
    caller_role: str = "unknown"
    global_goal: str
    context: dict[str, Any] = {}
    attachments: list[TaskAttachment] = []
    caller_device_key: str
    root_thread_id: str
    parent_thread_id: str
    hop_count: int = 1
    max_hops: int = 3
    timeout_seconds: int = 600


class AgentTaskResult(DynamicBaseModel):
    """A2A 任务执行完毕的回调信封"""

    task_id: str
    status: str  # "success" | "failed" | "cancelled" | "timeout"
    summary: str = ""
    error: str = ""
    attachments: list[TaskAttachment] = []
