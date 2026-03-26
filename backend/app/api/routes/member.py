import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.api.deps import TokenDep
from app.core.evocloud import evocloud_manager
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.identity import identity_service

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
