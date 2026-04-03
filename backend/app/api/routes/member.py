import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.api.deps import TokenDep
from app.core.evocloud import evocloud_manager
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.identity import identity_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["member"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    result = await evocloud_manager.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(
            status_code=401, detail=result.get("message", "Login failed")
        )

    # Process login via IdentityService and return local JWT
    local_token = await identity_service.login_with_cloud_result(result)
    if not local_token:
         raise HTTPException(status_code=500, detail="Failed to initialize local session")

    # Update result to return local token
    result["token"] = local_token

    # Cache for fast access in deps.py
    user_data = result.get("data", {})
    member_id = result.get("member_id", 0)
    if user_data and member_id:
        try:
            from app.services.cache_services import UserCacheService
            user_cache = UserCacheService()
            await user_cache.set_user(member_id, user_data)
        except Exception:
            pass

    return result


@router.get("/status")
async def status():
    # Return basic status
    return {
        "is_logged_in": bool(evocloud_manager.get_token()),
        "device_id": evocloud_manager.device_id,
        "is_connected": evocloud_manager.link.is_connected() if evocloud_manager.link else False
    }


@router.post("/logout")
async def logout():
    # Logout logic: Clear token and stop link
    identity_service.logout()

    if evocloud_manager.api:
        evocloud_manager.api.set_token(None)
    if evocloud_manager.link:
        await evocloud_manager.link.stop()

    # Clear cache token (Unified logic in client logout? No, client logout clears local state)
    # But for cache (server-side session-ish), let's keep it clean or move to client.
    # The client uses cache for caching token? No, Client uses file.


@router.get("/cancellation/info")
async def get_cancellation_info(_token: TokenDep):
    return await evocloud_manager.api.get_cancellation_info()


@router.post("/cancellation/apply")
async def apply_cancellation(_token: TokenDep):
    return await evocloud_manager.api.apply_cancellation()


@router.post("/cancellation/cancel")
async def cancel_cancellation(_token: TokenDep):
    return await evocloud_manager.api.cancel_cancellation_apply()


# --- Subscription & Quota ---

@router.get("/subscription/plans")
async def get_subscription_plans(_token: TokenDep):
    """获取可用订阅计划"""
    return await evocloud_manager.api.get_subscription_plans()


@router.post("/subscription/upgrade-preview")
async def calculate_upgrade_price(target_level_id: int, _token: TokenDep):
    """计算升级价格预览（支付前调用）
    
    返回：
    - current_level: 当前等级信息
    - target_level: 目标等级信息
    - upgrade_calculation: 升级计算详情
        - is_upgrade: 是否是升级
        - pay_amount: 需支付金额
        - refund_amount: 将退还金额
        - net_amount: 净支付金额
        - total_duration: 总有效期（天）
        - quota_diff: 额度补差
    """
    return await evocloud_manager.api.calculate_upgrade_price(target_level_id)


@router.get("/subscription/status")
async def get_subscription_status(_token: TokenDep):
    """获取订阅状态"""
    return await evocloud_manager.api.get_subscription_status()


@router.get("/subscription/detail")
async def get_subscription_detail(_token: TokenDep):
    """获取订阅详情"""
    return await evocloud_manager.api.get_subscription_detail()


class CreateOrderRequest(BaseModel):
    level_id: int
    auto_renew: bool = False


@router.post("/subscription/order")
async def create_subscription_order(req: CreateOrderRequest, _token: TokenDep):
    """创建订阅订单"""
    return await evocloud_manager.api.create_subscription_order(req.level_id, req.auto_renew)


@router.post("/subscription/cancel")
async def cancel_subscription(cancel_type: str = "expire", reason: str = "", _token: TokenDep = None):
    """取消订阅"""
    return await evocloud_manager.api.cancel_subscription(cancel_type, reason)


@router.get("/subscription/order/status")
async def check_subscription_order_status(
    order_id: str,
    _token: TokenDep,
):
    """
    检查订阅订单状态
    """
    return await evocloud_manager.api.check_subscription_order_status(order_id)

@router.get("/quota")
async def get_ai_quota(_token: TokenDep):
    """获取主要 AI 配额 (统一配额池)"""
    return await evocloud_manager.api.get_ai_quota()


@router.get("/quota/all")
async def get_all_ai_quotas(_token: TokenDep):
    """获取所有 AI 配额"""
    return await evocloud_manager.api.get_all_ai_quotas()


@router.get("/quota/history")
async def get_ai_quota_history(page: int = 1, page_size: int = 20, _token: TokenDep = None):
    """获取配额使用历史"""
    return await evocloud_manager.api.get_ai_quota_history(page, page_size=page_size)


# --- Batch Benefits & Cache Management ---

from typing import List
from app.api.deps import (
    get_member_benefits, 
    check_multiple_benefits, 
    invalidate_benefits_cache,
    BENEFIT_NAME_MAP
)


class BatchCheckRequest(BaseModel):
    benefit_codes: List[str]


class BatchCheckResponse(BaseModel):
    results: dict[str, bool]
    is_expired: bool
    level_name: str


@router.post("/benefits/check-batch", response_model=BatchCheckResponse)
async def check_benefits_batch(req: BatchCheckRequest, token: TokenDep):
    """
    批量检查多项权益
    
    性能优化：只查询一次API，同时检查多个权益
    
    Example:
        POST /member/benefits/check-batch
        {"benefit_codes": ["voice", "desktop_control", "browser_control"]}
        
        Response:
        {
            "results": {
                "voice": true,
                "desktop_control": false,
                "browser_control": true
            },
            "is_expired": false,
            "level_name": "极客版"
        }
    """
    # 批量检查权益
    results = await check_multiple_benefits(req.benefit_codes, token)
    
    # 获取额外信息
    benefits_data = await get_member_benefits(token)
    
    return BatchCheckResponse(
        results=results,
        is_expired=benefits_data.get("is_expired", False),
        level_name=benefits_data.get("level_name", "免费用户")
    )


@router.get("/benefits")
async def get_member_benefits_api(
    force_refresh: bool = False,
    token: TokenDep = None
):
    """
    获取会员完整权益信息
    
    Args:
        force_refresh: 是否强制刷新缓存
    """
    data = await get_member_benefits(token, force_refresh=force_refresh)
    return {
        "code": 0,
        "data": data
    }


@router.post("/benefits/cache/invalidate")
async def invalidate_member_benefits_cache(token: TokenDep):
    """
    手动使权益缓存失效（用于调试或强制刷新）
    """
    invalidate_benefits_cache(token)
    return {
        "code": 0,
        "message": "缓存已清除"
    }


# --- Webhook for Benefits Update ---

class BenefitsUpdateWebhook(BaseModel):
    member_id: int
    event: str  # "subscription_created", "subscription_renewed", "subscription_cancelled"
    level_id: int | None = None
    timestamp: int
    signature: str  # HMAC签名用于验证


@router.post("/webhook/benefits-update")
async def handle_benefits_update_webhook(payload: BenefitsUpdateWebhook):
    """
    接收来自PHP后端的权益更新Webhook
    
    当会员订阅状态变更时，PHP后端会调用此接口通知Python后端刷新缓存
    
    Events:
    - subscription_created: 新订阅创建
    - subscription_renewed: 订阅续费
    - subscription_upgraded: 订阅升级
    - subscription_cancelled: 订阅取消
    - subscription_expired: 订阅过期
    """
    import hmac
    import hashlib
    
    # 验证签名（使用与PHP相同的密钥）
    from app.core.config import settings
    webhook_secret = getattr(settings, "WEBHOOK_SECRET", "")
    
    if webhook_secret:
        expected_signature = hmac.new(
            webhook_secret.encode(),
            f"{payload.member_id}:{payload.event}:{payload.timestamp}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(payload.signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # 根据事件类型处理
    logger = logging.getLogger(__name__)
    logger.info(f"[Webhook] Received benefits update: {payload.event} for member {payload.member_id}")
    
    # 清除该用户的所有缓存（无法知道具体token，清除全部）
    if payload.event in ["subscription_created", "subscription_renewed", "subscription_upgraded"]:
        invalidate_benefits_cache()
        logger.info(f"[Webhook] Benefits cache invalidated due to {payload.event}")
    
    return {
        "code": 0,
        "message": "Webhook processed successfully"
    }
