"""API schemas for project duty (customer-service + business poll)."""

from pydantic import StrictInt

from app.infrastructure.pydantic_base import DynamicBaseModel


class BusinessPollPrompt(DynamicBaseModel):
    """业务巡检任务（一条独立的 Agent 会话）。"""

    id: str
    prompt: str
    # 下次执行时间（ISO 8601，带时区）
    next_run_at: str
    # 执行间隔（分钟）
    interval_minutes: StrictInt
    enabled: bool = True


class DutyConfig(DynamicBaseModel):
    """值守配置（项目 project.json 的 customer_service_duty 字段）。

    全字段可选 = 部分更新语义（PUT）：未传字段保持原值。

    轮巡间隔/业务巡检扫描间隔属于全局值守设置（CUSTOMER_SERVICE_DUTY），
    不在项目级配置；项目只负责参与意愿（enabled）+ 渠道（channels）+
    巡检任务列表（business_poll_prompts）。
    """

    enabled: bool | None = None
    # 兼容新旧格式：dict（{"wecom": {...}, "callback": {...}}）或旧数组（["wecom"]）
    channels: dict | list | None = None
    # 业务巡检任务列表；每条到点后作为独立 human 消息发给 Agent（thread_id=""）。
    business_poll_prompts: list[BusinessPollPrompt] | None = None


__all__ = ["BusinessPollPrompt", "DutyConfig"]
