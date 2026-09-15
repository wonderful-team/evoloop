"""任务域跨边界强类型（Pydantic 模型）。

服务层与工具/API/模板之间透传的模型；仅在响应序列化边界才转 dict。
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.pydantic_base import DynamicBaseModel


class WakeupTask(DynamicBaseModel):
    """唤醒 prompt 的单任务载荷（dispatcher → 模板渲染）。"""

    id: str
    status: str
    title: str
    instruction: str
    priority: str
    risk: str
    due: str
    feedback: str = ""


class DashboardPayload(DynamicBaseModel):
    """自主值守看板聚合（GET /tasks/queue/dashboard 的响应体）。"""

    success: bool = True
    counts: dict[str, int]
    duty_state: str
    tokens: dict[str, Any]
    today_window: dict[str, Any]
    current_run: dict[str, Any] | None
    daily: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    awaiting_human: list[dict[str, Any]]
