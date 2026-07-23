"""API schemas for subscription routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class CreateOrderRequest(DynamicBaseModel):
    level_id: int
    auto_renew: bool = False
    pay_type: str = "wechatpay"

class BenefitsUpdateWebhook(DynamicBaseModel):
    member_id: int
    event: str  # "subscription_created", "subscription_renewed", "subscription_cancelled"
    level_id: int | None = None
    timestamp: int
    signature: str  # HMAC签名用于验证

class SubscriptionWebhookResponse(BaseAPIResponse):
    """Webhook processing response."""
    code: int
