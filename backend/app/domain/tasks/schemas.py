"""任务域跨边界强类型（Pydantic 模型）。

服务层与工具/API/模板之间透传的模型；仅在响应序列化边界才转 dict。
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.pydantic_base import DynamicBaseModel


class WorkflowStageSpec(DynamicBaseModel):
    """周期工作流的阶段模板（create_workflow 入参；deps 用阶段 key 引用）。"""

    key: str
    title: str
    description: str = ""
    category: str | None = None
    priority: str = "medium"
    risk_level: str | None = None
    deps: list[str] = []
    skills: list[str] = []
    acceptance_criteria: list[str] = []


class DashboardPayload(DynamicBaseModel):
    """自主值守看板聚合（GET /tasks/queue/dashboard 的响应体）。"""

    success: bool = True
    counts: dict[str, int]
    duty_state: str
    duty_enabled: bool = False
    tokens: dict[str, Any]
    today_window: dict[str, Any]
    current_run: dict[str, Any] | None
    daily: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    awaiting_human: list[dict[str, Any]]
    workflows: list[dict[str, Any]] = []
