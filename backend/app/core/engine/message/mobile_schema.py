"""
MobileMessage Schema — Agent → Mobile 统一消息协议。

定义 Agent 通过 WebSocket 推送给 Mobile 的所有消息类型的 Pydantic 模型，
替代原来 handler.py 中裸字典构造的隐性协议。
"""
from typing import Any, Literal

from app.infrastructure.pydantic_base import DynamicBaseModel


class MobileSyncMessage(DynamicBaseModel):
    """
    Agent 通过 message_sync 推送给 Mobile 的单条消息。

    字段与 handler.py _push_to_mobile() 发送的裸字典完全一致，
    用于显式化协议、提供 IDE 类型提示和运行时校验。
    """

    id: str
    thread_id: str
    project_id: int = 0
    role: Literal["human", "ai", "tool", "system"]
    content: str = ""
    thinking: str | None = None
    created_at: int
    sequence_number: int
    action_type: str = "text"
    is_visible: int = 1
    status: Literal["completed", "failed", "waiting_human"] = "completed"
    category: str = ""

    # 可选：工具调用相关
    tool_calls: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None


class MobileCommandComplete(DynamicBaseModel):
    """
    Agent 运行完成信号，通过 command_complete 推送给 Mobile。
    """

    thread_id: str
    command_id: int | str = 0
    status: Literal["done", "failed", "cancelled"] = "done"
