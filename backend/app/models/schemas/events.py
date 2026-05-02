"""
SSE 流式事件 Schema —— 全系统通用事件定义。

职责：
1. 定义非消息特定的流式事件（ArtifactEvent, TokenEvent 等）
2. 消息特定事件（BlockEvent, HumanRequestEvent）从消息模块导入

架构位置：
- 通用事件 → app.models.schemas.events（此文件）
- 消息/引擎特定事件 → app.core.engine.message.schemas
"""

from enum import Enum
from typing import Any, Dict, Literal, Optional, Union

# Re-export message-specific events that downstream code expects from this module
from app.core.engine.message.schemas import HumanRequestEvent  # noqa: F401
from app.infrastructure.pydantic_base import EventBase


class StreamEventType(str, Enum):
    """Canonical stream event types for real-time UI updates.

    Includes all values from app.core.engine.callbacks.transparent.StreamEventType
    plus additional error/auth types used in the SSE stream endpoint.
    """
    THINKING = "thinking"
    PROGRESS = "progress"
    COMPLETE = "complete"
    LLM_AUTH_ERROR = "llm_auth_error"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH_EXPIRED = "auth_expired"


# --- Artifact Events ---
class ArtifactPayload(EventBase):
    name: str
    artifact_type: str  # "code", "design", "log"
    path: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ArtifactEvent(EventBase):
    type: Literal["artifact"] = "artifact"
    action: Literal["create", "update"] = "create"
    name: str = ""
    data: Union[ArtifactPayload, Dict[str, Any]]


# --- Agent State Events ---
class AgentStateEvent(EventBase):
    type: Literal["state"] = "state"
    action: Literal["update"] = "update"
    data: Dict[str, Any]


# --- Token Events ---
class TokenEvent(EventBase):
    type: Literal["token"] = "token"
    content: str


# --- Error/Status Events ---
class StatusEvent(EventBase):
    type: Literal["status"] = "status"
    status: str
    message: Optional[str] = None


# --- Quota Exhausted Event ---
class QuotaExhaustedEvent(EventBase):
    type: Literal["quota_exhausted"] = "quota_exhausted"
    title: str = "Quota Exhausted"
    message: str = "Your LLM quota has been exhausted."
    hint: str = "Please contact the administrator to add more quota."
    action_text: str = "Check Quota"
