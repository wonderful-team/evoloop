"""
Message System Core Schema —— 全链路标准化消息结构。

职责：
1. 定义贯穿 DB / API / SSE / Mobile 的核心消息 Block
2. 所有字段命名、类型、格式在此文件统一

命名约定：
- *Block：全链路标准化的数据块（MessageBlock, ToolBlock, HITLBlock）
- BlockEvent：SSE 流式事件的包装器
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel, EventBase
from app.utils.time import format_iso_timestamp


class ThinkingBlock(DynamicBaseModel):
    """
    思考过程块 —— 结构化推理内容。
    """
    type: Literal["reasoning", "audit"] = "reasoning"
    content: str


class ToolBlock(DynamicBaseModel):
    """
    工具执行块 —— 全链路标准化。
    """
    id: str
    tool_call_id: str
    tool: str                                    # 原始标识符，如 "read_file"
    tool_name: str | None = None                 # 显示名回退（当前与 tool 相同）
    name: str | None = None                      # 人类可读显示名（来自 tool_meta 或 i18n）
    input: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    status: Literal["pending", "running", "done", "failed"] = "pending"
    duration_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tool_meta: dict[str, Any] | None = None


class MessageBlock(DynamicBaseModel):
    """
    消息块 —— 全链路标准化消息结构。

    原则：
    1. 字段名全系统统一，变更需走版本升级流程
    2. 时间戳统一使用 ISO 8601 字符串（时区敏感）
    3. ID 统一使用 "msg-{thread_id}-{seq}"，与数据库 sequence_number 绑定
    4. 思考过程统一为结构化数组，支持多段推理
    5. 禁止在结构中直接嵌入裸字典
    """

    # === 核心标识 ===
    id: str                                        # "msg-{thread_id}-{sequence_number}"
    thread_id: str
    run_id: str | None = None

    # === 角色与分类 ===
    role: Literal["human", "ai", "tool", "system"]
    category: str = ""                             # MessageCategory.value

    # === 内容 ===
    content: str = ""
    content_type: Literal["text", "markdown", "json", "multipart"] = "text"

    # === 思考过程 ===
    thinking: str | None = None

    # === 工具调用 ===
    tool_calls: list[dict[str, Any]] | None = None
    steps: list[ToolBlock] | None = None  # Folded tool execution steps (replaces tool_blocks)

    # === 状态与可见性 ===
    status: Literal["pending", "running", "streaming", "completed", "failed", "waiting_human"] = "completed"
    is_visible: bool = True

    # === 时间戳（统一 ISO 8601，时区敏感）===
    created_at: str = ""                           # e.g. "2024-01-15T10:30:00+08:00"
    updated_at: str | None = None

    # === 关联与元数据 ===
    sequence_number: int = 0
    parent_id: str | None = None
    checkpoint_id: str | None = None
    meta_data: dict[str, Any] = Field(default_factory=dict)

    # === 引用（知识/记忆/文件）===
    references: list[dict[str, Any]] | None = None


class BlockEvent(DynamicBaseModel):
    """
    SSE 流式事件 —— 替代 MessageEvent 中的裸字典 data。
    """
    type: Literal["message"] = "message"
    action: Literal["create", "update", "append"] = "create"
    data: MessageBlock


class StreamEvent(DynamicBaseModel):
    """
    结构化流式事件 —— 用于前端实时交互展示。
    """
    type: str                                      # StreamEventType
    message: str = ""
    data: dict[str, Any] | DynamicBaseModel | None = None
    progress: int | None = None
    timestamp: str = Field(default_factory=lambda: format_iso_timestamp())

    def to_json(self) -> str:
        """Convert to JSON string for SSE."""
        return self.model_dump_json(exclude_none=True)


class ThinkingPayload(DynamicBaseModel):
    """思考流事件的 data 负载"""
    detail: str = "reasoning"


class ToolProgressPayload(DynamicBaseModel):
    """工具进度流事件的 data 负载"""
    tool: str


class HITLBlock(DynamicBaseModel):
    """
    人机交互块 —— 取代之前三套独立结构。
    """
    id: str
    thread_id: str
    request_type: Literal["text_input", "choice", "confirmation", "file_select", "approval"]
    prompt: str
    description: str = ""
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    allow_cancel: bool = True
    status: Literal["pending", "completed", "cancelled", "timeout"] = "pending"
    result: dict[str, Any] | None = None
    created_at: str = ""                           # ISO 8601
    resolved_at: str | None = None


class HistoryBlock(MessageBlock):
    """
    API 历史记录响应块 —— 继承 MessageBlock，扩展展示层字段。
    """
    has_file_operations: bool = False
    changeset_count: int = 0


class MessageHandlerResult(DynamicBaseModel):
    category: str
    persisted: bool
    streamed: bool
    message_id: str | None = None
    sequence_number: int = 0
    reason: str | None = None


class PersistencePolicyResult(DynamicBaseModel):
    should_persist: bool
    content: str | None = None
    thinking: str | None = None
    tool_calls: list | None = None
    category: str
    tool_call_id: str | None = None
    tool_name: str | None = None


class StreamPolicyResult(DynamicBaseModel):
    should_stream: bool
    frontend_type: str | None = None
    content: str
    category: str
    metadata: dict = {}


class HumanRequestEvent(EventBase):
    """
    人机交互请求事件。

    数据字段使用 HITLBlock，与消息系统共享同一套结构。
    保留此模型以便现有代码平滑迁移。
    新代码建议使用 BlockEvent 包装 HITLBlock 替代。
    """
    type: Literal["human_request"] = "human_request"
    action: Literal["create", "update", "clear"] = "create"
    data: HITLBlock | dict[str, Any]
