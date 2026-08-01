import hmac
import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import TokenDep
from app.api.schemas.subscription import (
    BenefitsUpdateWebhook,
    CreateOrderRequest,
    SubscriptionWebhookResponse,
)
from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.core.benefits import benefit_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscription"])

# --- Subscription Plans & Status ---

@router.get("/subscription/plans")
async def get_subscription_plans(_token: TokenDep):
    """获取可用订阅计划"""
    return await evocloud_manager.api.get_subscription_plans(token=_token)

@router.post("/subscription/upgrade-preview")
async def calculate_upgrade_price(target_level_id: int, _token: TokenDep):
    """计算升级价格预览"""
    return await evocloud_manager.api.calculate_upgrade_price(target_level_id, token=_token)

@router.get("/subscription/status")
async def get_subscription_status(_token: TokenDep):
    """获取订阅状态"""
    return await evocloud_manager.api.get_subscription_status(token=_token)

@router.get("/subscription/detail")
async def get_subscription_detail(_token: TokenDep):
    """获取订阅详情"""
    return await evocloud_manager.api.get_subscription_detail(token=_token)

@router.post("/subscription/order")
async def create_subscription_order(req: CreateOrderRequest, _token: TokenDep):
    """创建订阅订单"""
    return await evocloud_manager.api.create_subscription_order(req.level_id, req.auto_renew, req.pay_type, token=_token)

@router.post("/subscription/cancel")
async def cancel_subscription(cancel_type: str = "expire", reason: str = "", _token: TokenDep = None):
    """取消订阅"""
    return await evocloud_manager.api.cancel_subscription(cancel_type, reason, token=_token)

@router.get("/subscription/order/status")
async def check_subscription_order_status(
    order_id: str,
    _token: TokenDep,
):
    """
    检查订阅订单状态
    """
    return await evocloud_manager.api.check_subscription_order_status(order_id, token=_token)

# --- AI Quota ---

@router.get("/quota")
async def get_ai_quota(_token: TokenDep):
    """获取主要 AI 配额 (统一配额池)"""
    return await evocloud_manager.api.get_ai_quota(token=_token)

@router.get("/quota/all")
async def get_all_ai_quotas(_token: TokenDep):
    """获取所有 AI 配额"""
    return await evocloud_manager.api.get_all_ai_quotas(token=_token)

@router.get("/quota/history")
async def get_ai_quota_history(page: int = 1, page_size: int = 20, _token: TokenDep = None):
    """获取配额使用历史"""
    return await evocloud_manager.api.get_ai_quota_history(page, page_size=page_size, token=_token)

# --- Webhook for Benefits Update ---

@router.post("/webhook/benefits-update")
async def handle_benefits_update_webhook(payload: BenefitsUpdateWebhook):
    """
    接收来自PHP后端的权益更新Webhook

    当会员订阅状态变更时，PHP后端会调用此接口通知Python后端刷新缓存
    """
    # 验证签名（使用与PHP相同的密钥）
    webhook_secret = settings.WEBHOOK_SECRET

    if webhook_secret:
        expected_signature = hmac.new(
            webhook_secret.encode(),
            f"{payload.member_id}:{payload.event}:{payload.timestamp}".encode(),
            "sha256"
        ).hexdigest()

        if not hmac.compare_digest(payload.signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 根据事件类型处理
    logger.info(f"[Webhook] Received benefits update: {payload.event} for member {payload.member_id}")

    # 清除该用户的所有缓存
    if payload.event in [
        "subscription_created", "subscription_renewed", "subscription_upgraded",
        "subscription_expired", "subscription_cancelled"
    ]:
        benefit_service.invalidate_cache(payload.member_id)
        logger.info(f"[Webhook] Benefits cache invalidated due to {payload.event}")

        # Notify frontend of subscription change via SSE
        try:
            from app.core.events.publishers import publish_subscription_changed
            await publish_subscription_changed(
                member_id=payload.member_id,
                event=payload.event,
            )
        except Exception as e:
            logger.warning(f"[Webhook] Failed to publish subscription changed event: {e}")

    return SubscriptionWebhookResponse(
        code=0,
        message="Webhook processed successfully"
    )
