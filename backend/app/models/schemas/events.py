"""
SSE 流式事件 Schema —— 全系统通用事件定义。

职责：
1. 定义非消息特定的流式事件（ArtifactEvent, TokenEvent 等）
2. 消息特定事件（BlockEvent, HumanRequestEvent）从消息模块导入

架构位置：
- 通用事件 → app.models.schemas.events（此文件）
- 消息/引擎特定事件 → app.core.engine.message.schemas
"""

from typing import Any, Dict, Literal, Union

from pydantic import model_validator

from app.core.events.base import BaseEvent


# --- Base Class for all SSE/Stream Events ---
class BaseStreamEvent(BaseEvent):
    """全系统流式协议基类：统一字段、平铺结构、高性能序列化"""
    type: str
    thread_id: str | None = None
    
    # Governance: Stream events are always public to the chat channel by default
    is_public: bool = True
    broadcast_channel: str = "chat"

    @model_validator(mode="after")
    def sync_stream_metadata(self) -> "BaseStreamEvent":
        """Link internal event_type for routing."""
        self.event_type = f"stream.{self.type}"
        return self

    def to_frontend_payload(self) -> dict:
        """高性能序列化入口"""
        return self.model_dump(exclude_none=True)
    
    def to_json(self) -> str:
        """Backward compatibility for legacy bus calls"""
        return self.model_dump_json(exclude_none=True)


# --- 1. 高频文本流：LLM Tokens ---
class TokenEvent(BaseStreamEvent):
    type: Literal["token"] = "token"
    content: str
    message_id: str | None = None


# --- 2. 思考过程流：Reasoning/Thinking ---
class ThinkingEvent(BaseStreamEvent):
    type: Literal["thinking"] = "thinking"
    content: str
    is_delta: bool = True
    message_id: str | None = None


# --- 3. 进度与工具执行流 ---
class ProgressEvent(BaseStreamEvent):
    type: Literal["progress"] = "progress"
    status: Literal["running", "success", "failed", "interrupted"] = "running"
    message: str = ""                                # 给用户看的显示文案
    progress: int | None = None                   # 0-100
    metadata: Dict[str, Any] = {}                    # 扩展信息：如 tool_name, call_id


# --- 4. 状态同步流：通用 UI 状态更新 ---
class StatusEvent(BaseStreamEvent):
    type: Literal["status"] = "status"
    status: str                                      # 内部状态码
    message: str | None = None                    # 显示消息


# --- 5. 资源流：Artifacts (Files, Shell, etc.) ---
class ArtifactEvent(BaseStreamEvent):
    type: Literal["artifact"] = "artifact"
    id: str
    name: str
    kind: str                                        # file, shell, terminal
    status: str                                      # pending, success, failed
    path: str | None = None
    content: str | None = None


# --- 6. 智能体全局状态流 ---
class AgentStateEvent(BaseStreamEvent):
    type: Literal["agent_state"] = "agent_state"
    mode: str                                        # PLANNING, EXECUTING
    task_name: str | None = None
    task_status: str | None = None
    active_skills: list[dict] | None = None       # [{id, name, description}] — Worker 实际挂载的技能


# --- 7. 消息块同步流：同步全量 MessageBlock ---
class MessageSyncEvent(BaseStreamEvent):
    type: Literal["message"] = "message"
    action: Literal["create", "update", "append"] = "create"
    data: "MessageBlock"                             # Forward ref to avoid circular import

    def to_json(self) -> str:
        # Special handling for MessageBlock which might need exclude_none on its data field
        return self.model_dump_json(exclude_none=True)


# --- 8. 人机交互请求事件 ---
class HumanRequestEvent(BaseStreamEvent):
    type: Literal["human_request"] = "human_request"
    action: str                                      # create, clear, update
    id: str | None = None
    prompt: str | None = None
    request_type: str | None = None
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    allow_cancel: bool = True
    payload: Dict[str, Any] = {}


# --- 9. 异常与资源事件 ---
class QuotaExhaustedEvent(BaseStreamEvent):
    type: Literal["quota_exhausted"] = "quota_exhausted"
    title: str = "Quota Exhausted"
    message: str = "Your LLM quota has been exhausted."
    hint: str = "Please contact the administrator to add more quota."


class AuthExpiredEvent(BaseStreamEvent):
    type: Literal["auth_expired"] = "auth_expired"
    title: str = "Auth Expired"
    message: str = "Session expired, please login again."
    hint: str | None = None


class LLMAuthErrorEvent(BaseStreamEvent):
    type: Literal["llm_auth_error"] = "llm_auth_error"
    title: str = "LLM Auth Failed"
    message: str = "Invalid API Key or expired."
    hint: str | None = None


# --- 10. 运行生命周期流 ---
class RunStartEvent(BaseStreamEvent):
    type: Literal["run_start"] = "run_start"
    run_id: str | None = None
    goal: str | None = None


class RunEndEvent(BaseStreamEvent):
    type: Literal["run_end"] = "run_end"
    run_id: str | None = None
    status: Literal["done", "failed", "cancelled", "interrupted"]
    final_outcome: str | None = None


# Type alias for all possible stream events
StreamEvent = Union[
    TokenEvent,
    ThinkingEvent,
    ProgressEvent,
    ArtifactEvent,
    AgentStateEvent,
    MessageSyncEvent,
    HumanRequestEvent,
    QuotaExhaustedEvent,
    AuthExpiredEvent,
    LLMAuthErrorEvent,
    RunStartEvent,
    RunEndEvent
]

# Type-safe import of MessageBlock for type checking
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.engine.message.schemas import MessageBlock

# Rebuild models that use forward references
def rebuild_event_models():
    from app.core.engine.message.schemas import MessageBlock  # noqa: F401
    MessageSyncEvent.model_rebuild()

try:
    rebuild_event_models()
except ImportError:
    # This might happen during initialization if schemas.py is not yet available
    pass
