"""
Core Event System - Shared Event Type Registry

Registry for cross-domain event types that are used by multiple modules.
Module-specific event types should be defined in their respective modules.
"""

from enum import Enum

from app.core.events.base import BaseEvent


class SystemEventType(str, Enum):
    """
    System-wide event types.

    These are cross-domain events that multiple modules may be interested in.
    """

    # Lifecycle Events
    APP_STARTED = "system.app_started"
    APP_STOPPING = "system.app_stopping"

    # Context Polishing
    # Published by Engine after context hydration. Subscribed by Domain experts to enrich/clean context.
    CONTEXT_POLISHING = "system.context_polishing"

    # Engine Lifecycle
    SESSION_STARTED = "system.session_started"
    SESSION_COMPLETED = "system.session_completed"
    EXTRACTION_REQUESTED = "system.extraction_requested"
    EXTRACTION_COMPLETED = "system.extraction_completed"
    WEBSOCKET_MESSAGE_RECEIVED = "websocket.message_received"
    # 服务端主动推送的任意 MCP notification（method 与 payload 在 event.data 中）
    MCP_SERVER_NOTIFICATION = "mcp.server_notification"
    # 第三方消息源经 channel 归一化后的统一入站消息（唯一生产方 channel 层）
    INBOUND_MESSAGE = "channel.inbound_message"
    # 任务回复路由（domain 决策 → channel 传输的出站回复）
    OUTBOUND_REPLY = "channel.outbound_reply"

    # Conversation Lifecycle
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_UPDATED = "conversation.updated"

    # Configuration Handlers
    CONFIG_CHANGED = "system.config_changed"
    STATE_CHANGED = "system.state_changed"

    # Awakening / Environment Events
    AWAKENING_COMPLETE = "system.awakening_complete"
    STATE_REFRESHED = "system.state_refreshed"
    BOUNDARY_LEARNED = "system.boundary_learned"

    # Authentication Events
    USER_LOGGED_IN = "system.user_logged_in"
    USER_LOGGED_OUT = "system.user_logged_out"

    # External Service / Infrastructure Events
    EMBEDDING_UPDATED = "system.embedding_updated"

    # Skill Lifecycle Events
    SKILL_CREATED = "learning.skill_created"
    SKILL_UPDATED = "learning.skill_updated"
    SKILL_DELETED = "learning.skill_deleted"

    # Macro Lifecycle Events
    MACRO_CREATED = "learning.macro_created"
    MACRO_UPDATED = "learning.macro_updated"
    MACRO_DELETED = "learning.macro_deleted"
    MACRO_OBSOLETED = "learning.macro_obsoleted"

    # Subscriptions & Logs
    SUBSCRIPTION_CHANGED = "subscription.changed"
    SYSTEM_LOG_ENTRY = "system.log_entry"
    PLAN_UPDATED = "plan.updated"
    ARTIFACT_VALIDATION = "system.artifact_validation"


class ArtifactValidationEvent(BaseEvent):
    """Event triggered to request verification of an artifact's physical database presence."""

    event_type: str = SystemEventType.ARTIFACT_VALIDATION
    project_id: int
    item: str
    is_valid: bool = True


class InboundMessageEvent(BaseEvent):
    """第三方入站消息（channel 归一化后的唯一形态）。

    生产方：app.core.channel.input.mcp_message —— 所有第三方 MCP 消息源
    经 ``notifications/mcp_message`` 通知进入，在此归一化为强类型事件。
    消费方：app.domain.tasks（消息 → 任务入队）；``contact`` 为会话类
    消息的回复路由元数据，缺省 = 纯工作项（无需回复）。
    """

    event_type: str = SystemEventType.INBOUND_MESSAGE
    source_system: str  # 来源 MCP server 名（provenance）
    event_id: str  # 幂等键（推送方保证同事件重投同 id）
    project_id: int = 0
    title: str
    content: str = ""
    contact: str | None = None
    channel: str = ""  # 来源渠道名（回复路由用，落 task.source_ref.channel）
    category: str | None = None
    priority: str = "medium"
    risk_level: str | None = None
    start_in_hours: float | None = None


class OutboundReplyEvent(BaseEvent):
    """任务回复路由事件（domain 决策「发给谁」，channel 传输「怎么发」）。

    生产方：app.domain.tasks（wakeup 会话终态按 task.source_ref 反查）。
    消费方：目标渠道（channel 名匹配）执行发送；纯工作项（无 contact）
    不产生本事件。
    """

    event_type: str = SystemEventType.OUTBOUND_REPLY
    channel: str  # 目标渠道名（如 mcp_message）
    recipient: str  # 联系人（contact）
    content: str  # 回复文本
    project_id: int = 0
    source_system: str = ""  # 来源 MCP server 名（渠道定位回复目标）
    thread_id: str | None = None


# Note: Module-specific event types are defined in their respective modules:
# - AgentEventType -> app.core.engine.event.types
# - MacroEventType -> app.core.learning.macro.event.types
# - RewindEventType -> app.core.engine.rewind.event.types
# - Environment EventType -> app.core.environment.event.types
# - ProjectEventType -> app.core.project.event.types
# - IndexingEventType -> app.domain.codebase.event.types
# - FileSystemEventType -> app.core.file.event.types
# - ToolEventType -> app.core.tools.event.types
# - VisionEventType -> app.core.vision.event.types
