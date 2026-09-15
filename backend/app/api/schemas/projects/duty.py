"""API schemas for project duty (customer-service duty switch)."""

from app.infrastructure.pydantic_base import DynamicBaseModel


class DutyConfig(DynamicBaseModel):
    """值守配置（项目 project.json 的 customer_service_duty 字段）。

    全字段可选 = 部分更新语义（PUT）：未传字段保持原值。

    轮巡间隔属于全局值守设置（CUSTOMER_SERVICE_DUTY），不在项目级配置；
    项目只负责参与意愿（enabled）+ 渠道（channels）。业务巡检已迁移为
    任务队列的 recurring 任务（business_poll_prompts 已废弃）。
    """

    enabled: bool | None = None
    # 兼容新旧格式：dict（{"wecom": {...}, "callback": {...}}）或旧数组（["wecom"]）
    channels: dict | list | None = None


__all__ = ["DutyConfig"]
