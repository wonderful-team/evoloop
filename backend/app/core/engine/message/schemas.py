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

from app.infrastructure.pydantic_base import DynamicBaseModel


class MessageReference(DynamicBaseModel):
    """
    消息引用 —— 挂载在消息上的非文本产出物（全平台统一标准，与 mobile/ 及 DB 模型对齐）。

    支持的类型及其约定：
    - file       : 可下载文件（PDF、Excel、TXT 等）。target_id = 预览 URL
    - image      : 图片（截图、生成图）。target_id = 图片 URL 或物理路径
    - audio      : 音频（语音回复、上传音频）。target_id = 音频 URL 或路径
    - video      : 视频（上传或生成的视频）。target_id = 视频 URL 或路径
    - message    : 引用历史消息（点击跳转）。target_id = message UUID
    - artifact   : 可交互组件（echarts/mermaid/map/html/react）。target_id = artifact UUID
    - changeset  : 代码变更集（文件修改列表）。target_id = run_id
    - skill      : 技能引用。target_id = skill_id
    - directory  : 目录引用（target_id = 目录路径，meta_data 含相关目录元数据）
    """

    id: str
    type: Literal[
        "file",
        "image",
        "audio",
        "video",
        "message",
        "artifact",
        "changeset",
        "skill",
        "directory",
    ]
    target_id: str  # 资源路径、消息 ID、或唯一标识
    target_name: str  # 人类可读名称
    meta_data: dict[str, Any] = Field(
        default_factory=dict
    )  # 扩展字段（因表结构命名为 meta_data）


class ToolCall(DynamicBaseModel):
    """
    工具调用请求 —— AI 发出的执行指令。
    """

    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    type: Literal["tool_call"] = "tool_call"
    index: int | None = None


class ToolBlock(DynamicBaseModel):
    """
    工具执行块 —— 全链路标准化。
    """

    id: str
    tool_call_id: str
    tool: str  # 原始标识符，如 "read_file"
    tool_name: str | None = None  # 显示名回退（当前与 tool 相同）
    name: str | None = None  # 人类可读显示名（来自 tool_meta 或 i18n）
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
    3. ID 统一使用 DB UUID（主键），sequence_number 仅用于排序/分页
    4. 思考过程统一为结构化数组，支持多段推理
    5. 禁止在结构中直接嵌入裸字典
    """

    # === 核心标识 ===
    id: str  # DB primary key UUID
    thread_id: str
    run_id: str | None = None

    # === 角色与分类 ===
    role: Literal["human", "ai", "tool", "system"]
    category: str = ""  # MessageCategory.value

    # === 内容 ===
    content: str = ""
    content_type: Literal["text", "markdown", "json", "multipart"] = "text"

    # === 思考过程 ===
    thinking: str | None = None

    # === 工具调用与执行 (当 role='tool' 时使用) ===
    tool_calls: list[ToolCall] | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    input: Any | None = None
    tool_meta: dict[str, Any] | None = None

    # === 附件与引用 (标准化 MessageReference) ===
    references: list[MessageReference] | None = None

    # === 变更集预览 (由 Mapper 自动填充) ===
    has_file_operations: bool = False
    changeset_count: int = 0
    changeset_files: list[dict[str, Any]] | None = None
    status: Literal[
        "pending", "running", "streaming", "completed", "failed", "waiting_human"
    ] = "completed"
    is_visible: bool = True

    # === 时间戳（统一 ISO 8601，时区敏感）===
    created_at: str = ""  # e.g. "2024-01-15T10:30:00+08:00"
    updated_at: str | None = None

    # === 溯源标识 ===
    sequence_number: int = 0
    parent_id: str | None = None
    checkpoint_id: str | None = None
    is_complete: bool | None = None  # 显式完成状态

    # === A2A 设备标识 ===
    executor_device_key: str | None = None
    executor_device_name: str | None = None

    # === 消息来源 ===
    # values: "desktop", "mobile", "api"
    source: str | None = None

    meta_data: dict[str, Any] = Field(default_factory=dict)


class HITLBlock(DynamicBaseModel):
    """
    人机交互块 —— 取代之前三套独立结构。
    """

    id: str
    thread_id: str
    request_type: Literal[
        "text", "choice", "confirmation", "file_select", "approval", "project_switch"
    ]
    prompt: str
    description: str = ""
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    allow_cancel: bool = True
    status: Literal["pending", "completed", "cancelled", "timeout"] = "pending"
    result: dict[str, Any] | None = None
    created_at: str = ""  # ISO 8601
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


class ReferenceContext(DynamicBaseModel):
    content_blocks: list[dict[str, Any]]
    reference_notes: list[str]
    injected_message: str
    references: list[dict[str, Any]] = []
