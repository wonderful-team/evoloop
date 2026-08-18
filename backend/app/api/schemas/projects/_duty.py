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
    interval/business_poll_interval 用 StrictInt（禁止 "60"→60 之类 coercion），
    非法类型在 422 层被拒，与运行时校验语义一致（v6.3 起）。
    """

    enabled: bool | None = None
    channels: dict | None = None
    interval: StrictInt | None = None
    # 业务巡检检查间隔（分钟），最小 1：调度任务以此频率扫描 prompts 列表。
    business_poll_interval: StrictInt | None = None
    # 业务巡检任务列表；每条到点后作为独立 human 消息发给 Agent（thread_id=""）。
    business_poll_prompts: list[BusinessPollPrompt] | None = None


__all__ = ["BusinessPollPrompt", "DutyConfig"]
