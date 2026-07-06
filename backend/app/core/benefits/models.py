"""Benefit-related models and helpers."""

from app.core.benefits.service import benefit_service
from app.infrastructure.pydantic_base import DynamicBaseModel


class BenefitErrorDetail(DynamicBaseModel):
    """统一的权益错误详情."""

    code: str = "BENEFIT_REQUIRED"
    feature: str
    feature_name: str
    message: str
    required_plan: str = "订阅版本"
    current_level: str = "免费用户"
    upgrade_url: str = "#/subscription"


def create_benefit_error_detail(benefit_code: str, current_level: str | None = None) -> BenefitErrorDetail:
    """创建统一的权益错误详情."""
    feature_name = benefit_service.get_benefit_label(benefit_code)
    return BenefitErrorDetail(
        feature=benefit_code,
        feature_name=feature_name,
        message=f"需要开通「{feature_name}」权益才能使用此功能",
        current_level=current_level or "免费用户",
    )
