import json
import logging
from collections.abc import Generator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.evocloud import evocloud_manager
from app.core.identity import decode_local_jwt, identity_service
from app.services.cache_services import UserCacheService, RateLimitService
from app.models import User

logger = logging.getLogger(__name__)


# ========== Cloud Device Authentication ==========

async def verify_device_token(authorization: str = Header(..., description="Bearer {device_token}")) -> str:
    """
    Verify device token for cloud API endpoints.

    TODO: Implement proper JWT validation with device registry
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )

    token = authorization.replace("Bearer ", "")

    # TODO: Validate token against device registry
    # For now, accept any non-empty token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty device token"
        )

    return token


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

# Global OAuth2 Scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False)

TokenDep = Annotated[str, Depends(oauth2_scheme)]
TokenDepOptional = Annotated[str | None, Depends(oauth2_scheme_optional)]


async def get_current_user(token: TokenDep) -> User:
    try:
        # 1. Decode Local JWT
        payload = decode_local_jwt(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired local session",
            )

        member_id = payload.get("member_id")
        if member_id is None:
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")

        # 2. Try Cache first
        user_cache = UserCacheService()
        user_data = await user_cache.get_user(member_id)

        # 3. Fallback to Cloud fetch if cache miss
        if not user_data:
            cloud_token = identity_service.get_cloud_token()
            if not cloud_token:
                 raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No cloud credentials found")

            result = await evocloud_manager.api.get_user_info(cloud_token)
            if result.get("code") != 0:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cloud verification failed")

            user_data = result.get("data", {})
            # Cache it back
            await user_cache.set_user(member_id, user_data)

        if user_data:
            user_data["id"] = user_data.get("id") or user_data.get("member_id") or member_id

        # Map Member Center data to User model
        try:
            user = User.model_validate(user_data)
        except Exception as ve:
            logger.error(f"User validation failed for member {member_id}: {ve} | Data: {user_data}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incomplete user profile: {str(ve)} | MemberID: {member_id}",
            )

        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")

        return user
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected auth error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Auth error ({type(e).__name__}): {str(e)}",
        )


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(token: TokenDepOptional) -> User | None:
    if not token:
        return None
    try:
        return await get_current_user(token)
    except Exception:
        return None


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


# ==================== Subscription Permission Dependencies ====================

async def check_feature_permission(feature: str, token: TokenDep) -> bool:
    """
    检查会员是否有特定订阅功能权限
    
    Args:
        feature: 功能标识，如 "ai_chat", "premium_content" 等
        token: JWT token
        
    Returns:
        True if has permission, False otherwise
    """
    try:
        result = await evocloud_manager.api.check_feature_permission(feature)
        if result.get("code") == 0:
            return result.get("data", {}).get("has_permission", False)
        return False
    except Exception as e:
        logger.error(f"检查功能权限失败 [{feature}]: {e}")
        return False


def require_subscription_feature(feature: str):
    """
    FastAPI 依赖工厂：要求特定订阅功能权限
    
    Usage:
        @router.post("/chat")
        async def chat(
            req: ChatRequest,
            user: CurrentUser = Depends(require_subscription_feature("ai_chat"))
        ):
            ...
    """
    async def checker(token: TokenDep) -> User:
        user = await get_current_user(token)
        
        # 检查权限
        has_access = await check_feature_permission(feature, token)
        
        if not has_access:
            # 获取用户当前订阅信息用于错误提示
            try:
                sub_detail = await evocloud_manager.api.get_subscription_detail()
                current_level = sub_detail.get("data", {}).get("level_name", "免费用户")
            except:
                current_level = "未知"
                
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"需要订阅功能: {feature}",
                    "feature": feature,
                    "current_level": current_level,
                    "upgrade_url": "/subscription/plans",
                    "code": "SUBSCRIPTION_REQUIRED"
                }
            )
        
        return user
    
    return checker


async def check_ai_quota(quota_type: str, token: str | None = None) -> dict:
    """
    检查 AI 配额
    
    Returns:
        {"has_quota": True, "remaining": 50, "total": 100}
    """
    try:
        result = await evocloud_manager.api.get_ai_quota(quota_type)
        if result.get("code") == 0:
            data = result.get("data", {})
            remaining = data.get("remaining", 0)
            return {
                "has_quota": remaining > 0,
                "remaining": remaining,
                "total": data.get("total", 0),
                "used": data.get("used", 0)
            }
        return {"has_quota": False, "remaining": 0, "total": 0, "used": 0}
    except Exception as e:
        logger.error(f"检查 AI 配额失败 [{quota_type}]: {e}")
        # 失败时允许访问（降级策略）
        return {"has_quota": True, "remaining": -1, "error": str(e)}


def require_ai_quota(quota_type: str):
    """
    FastAPI 依赖工厂：要求 AI 配额
    
    Usage:
        @router.post("/chat")
        async def chat(
            req: ChatRequest,
            user: CurrentUser = Depends(require_ai_quota("ai_chat"))
        ):
            ...
    """
    async def checker(token: TokenDep) -> User:
        user = await get_current_user(token)
        
        quota_info = await check_ai_quota(quota_type, token)
        
        if not quota_info.get("has_quota"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"AI 配额已用完: {quota_type}",
                    "quota_type": quota_type,
                    "used": quota_info.get("used"),
                    "total": quota_info.get("total"),
                    "upgrade_url": "/subscription/plans",
                    "code": "QUOTA_EXHAUSTED"
                }
            )
        
        return user
    
    return checker


async def consume_ai_quota_dependency(
    quota_type: str,
    count: int = 1,
    metadata: dict | None = None
):
    """
    消耗 AI 配额的依赖函数
    
    Usage:
        @router.post("/chat")
        async def chat(
            req: ChatRequest,
            user: CurrentUser = Depends(require_ai_quota("ai_chat"))
        ):
            # 执行业务逻辑
            result = await do_chat(req)
            
            # 消耗配额
            await consume_ai_quota_dependency("ai_chat", count=1, metadata={"tokens": result.tokens})
            
            return result
    """
    try:
        result = await evocloud_manager.api.consume_ai_quota(quota_type, count, metadata)
        if result.get("code") != 0:
            logger.warning(f"消耗配额失败 [{quota_type}]: {result.get('message')}")
    except Exception as e:
        logger.error(f"消耗配额异常 [{quota_type}]: {e}")


# ==================== Guest Access ====================

async def verify_guest_access(
    current_user: CurrentUserOptional,
    x_guest_id: Annotated[str | None, Header()] = None,
    guest_id: str | None = None,  # Added for Query Param support
    token: str | None = None,  # Added for Query Param Token Support (SSE)
) -> None:
    """
    Middleware-like dependency to verify guest access limits.
    If 'current_user' is present, this check is skipped (Paid/Auth user).
    If no user, checks 'token' param manually (backfill current_user).
    If still no user, 'x_guest_id' is checked against cache daily limits.
    """
    # 0. Backfill User from Query Token if Header Auth missing
    if not current_user and token:
        try:
            # A. Try Local JWT first (Unified Flow)
            payload = decode_local_jwt(token)
            if payload:
                member_id = payload.get("member_id")
                if member_id is not None:
                    # It's a valid local session - Success
                    return

            # B. Fallback to Cloud fetch for direct cloud token usage (Legacy/SSE compat)
            result = await evocloud_manager.api.get_user_info(token)
            if result.get("code") == 0:
                user_data = result.get("data", {})
                if user_data:
                    return
        except Exception as e:
            logger.debug(f"Query token validation failed: {e}")
            pass

    if current_user:
        return

    # Resolve IDs
    effective_guest_id = x_guest_id or guest_id

    if not effective_guest_id:
        raise HTTPException(status_code=401, detail="Authentication required (or guest_id)")

    # Check Guest Limits via cache
    try:
        # 1. Get Global Config
        try:
            # Async call to global config
            config_res = await evocloud_manager.api.get_ai_global_config()
            limit = 10  # Default
            if config_res and config_res.get("code") == 0:
                limit = int(config_res.get("data", {}).get("guest_daily_limit", 10))
        except Exception as e:
            logger.warning(f"Failed to fetch guest config, using default: {e}")
            limit = 10

        if limit <= 0:
            raise HTTPException(status_code=403, detail="Guest chat disabled")

        # 2. Check Daily Usage
        rate_limit = RateLimitService()
        endpoint = "guest:usage"
        current_usage = await rate_limit.increment(
            endpoint, 
            effective_guest_id,
            window=86400  # 24h
        )

        if current_usage > limit:
            raise HTTPException(
                status_code=402,
                detail=f"Guest limit reached ({limit}/day). Please upgrade.",
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Cache error during guest check: {e}")
        # Fail-Close: If cache is down, we cannot verify quota, so we must deny to prevent abuse.
        raise HTTPException(status_code=503, detail="Guest validation service temporary unavailable.")
