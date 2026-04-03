import json
import logging
import time
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

# 权益到所需套餐的映射
BENEFIT_PLAN_MAP = {
    "browser_control": "极客版",
    "voice": "极客版",
    "skill_learning": "极客版",
    "knowledge_base": "极客版",
    "desktop_control": "专家版",
    "mobile_control": "专家版",
    "wiki_generation": "创作者版",
    "gantt": "企业版",
    "timesheet": "企业版",
}

# 权益中文名称映射
BENEFIT_NAME_MAP = {
    "browser_control": "浏览器控制",
    "desktop_control": "桌面控制",
    "mobile_control": "手机控制",
    "voice": "语音交互",
    "skill_learning": "技能学习",
    "wiki_generation": "Wiki生成",
    "gantt": "甘特图",
    "timesheet": "工时表",
    "knowledge_base": "知识库",
}

# 权益缓存配置
BENEFIT_CACHE_TTL = 30  # 30秒缓存，平衡性能和实时性
_benefits_cache: dict[str, tuple[dict, float]] = {}  # token -> (data, timestamp)


def _get_cache_key(token: str) -> str:
    """生成缓存键"""
    import hashlib
    return hashlib.md5(token.encode()).hexdigest()[:16]


def _get_cached_benefits(token: str) -> dict | None:
    """获取缓存的权益数据"""
    cache_key = _get_cache_key(token)
    if cache_key in _benefits_cache:
        data, timestamp = _benefits_cache[cache_key]
        if time.time() - timestamp < BENEFIT_CACHE_TTL:
            return data
    return None


def _set_cached_benefits(token: str, data: dict) -> None:
    """设置权益缓存"""
    cache_key = _get_cache_key(token)
    _benefits_cache[cache_key] = (data, time.time())


def invalidate_benefits_cache(token: str | None = None) -> None:
    """
    使权益缓存失效
    
    Args:
        token: 如果提供，仅使该token的缓存失效；否则清除所有缓存
    """
    global _benefits_cache
    if token:
        cache_key = _get_cache_key(token)
        _benefits_cache.pop(cache_key, None)
        logger.debug(f"[Benefits] Cache invalidated for token: {cache_key}")
    else:
        _benefits_cache.clear()
        logger.info("[Benefits] All cache cleared")


async def get_member_benefits(token: str, force_refresh: bool = False) -> dict:
    """
    获取会员权益配置
    
    Args:
        token: JWT token
        force_refresh: 是否强制刷新缓存
        
    Returns:
        权益数据字典
    """
    # 1. 尝试从缓存获取
    if not force_refresh:
        cached = _get_cached_benefits(token)
        if cached:
            logger.debug("[Benefits] Using cached benefits data")
            return cached
    
    # 2. 从API获取
    try:
        result = await evocloud_manager.api.get_member_benefits()
        if result.get("code") == 0:
            data = result.get("data", {})
            # 更新缓存
            _set_cached_benefits(token, data)
            return data
        return {}
    except Exception as e:
        logger.error(f"获取会员权益失败: {e}")
        # 如果API失败，尝试返回缓存数据（即使已过期）
        cached = _get_cached_benefits(token)
        if cached:
            logger.warning("[Benefits] API failed, using stale cache")
            return cached
        return {}


async def check_benefit(benefit_code: str, token: TokenDep) -> bool:
    """
    检查会员是否拥有特定权益
    
    Args:
        benefit_code: 权益编码，如 "desktop_control", "voice" 等
        token: JWT token
        
    Returns:
        True if has benefit, False otherwise
    """
    try:
        benefits_data = await get_member_benefits(token)
        benefits = benefits_data.get("benefits", {})
        
        # 检查权益值
        value = benefits.get(benefit_code, False)
        
        # 布尔类型直接返回
        if isinstance(value, bool):
            return value
        
        # 数值类型：大于0表示有权限
        if isinstance(value, (int, float)):
            return value > 0
        
        # 字符串类型：true/on/1 表示有权限
        if isinstance(value, str):
            return value.lower() in ("true", "on", "1", "yes")
        
        return False
    except Exception as e:
        logger.error(f"检查权益失败 [{benefit_code}]: {e}")
        return False


async def check_multiple_benefits(benefit_codes: list[str], token: TokenDep) -> dict[str, bool]:
    """
    批量检查多项权益（性能优化：只查询一次API）
    
    Args:
        benefit_codes: 权益编码列表
        token: JWT token
        
    Returns:
        dict: {benefit_code: has_access}
        
    Example:
        >>> results = await check_multiple_benefits(["voice", "desktop_control"], token)
        >>> print(results)  # {"voice": True, "desktop_control": False}
    """
    try:
        benefits_data = await get_member_benefits(token)
        benefits = benefits_data.get("benefits", {})
        
        result = {}
        for code in benefit_codes:
            value = benefits.get(code, False)
            
            # 统一转换为bool
            if isinstance(value, bool):
                result[code] = value
            elif isinstance(value, (int, float)):
                result[code] = value > 0
            elif isinstance(value, str):
                result[code] = value.lower() in ("true", "on", "1", "yes")
            else:
                result[code] = False
                
        return result
    except Exception as e:
        logger.error(f"批量检查权益失败: {e}")
        return {code: False for code in benefit_codes}


def create_benefit_error_detail(benefit_code: str, current_level: str | None = None) -> dict:
    """
    创建统一的权益错误详情
    
    Args:
        benefit_code: 权益编码
        current_level: 当前用户等级（可选）
        
    Returns:
        标准化的错误详情字典
    """
    return {
        "code": "BENEFIT_REQUIRED",
        "feature": benefit_code,
        "feature_name": BENEFIT_NAME_MAP.get(benefit_code, benefit_code),
        "message": f"需要订阅「{BENEFIT_NAME_MAP.get(benefit_code, benefit_code)}」功能才能使用此功能",
        "required_plan": BENEFIT_PLAN_MAP.get(benefit_code, "更高等级订阅"),
        "current_level": current_level or "免费用户",
        "upgrade_url": "#/subscription",
    }


def raise_benefit_required(benefit_code: str, current_level: str | None = None):
    """
    抛出统一的权益不足异常
    
    Args:
        benefit_code: 权益编码
        current_level: 当前用户等级（可选）
        
    Raises:
        HTTPException: 403 Forbidden with standardized detail
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=create_benefit_error_detail(benefit_code, current_level)
    )


def require_benefit(benefit_code: str):
    """
    FastAPI 依赖工厂：要求特定权益
    
    Usage:
        @router.post("/desktop/control")
        async def desktop_control(
            req: Request,
            _: bool = Depends(require_benefit("desktop_control"))
        ):
            ...
    """
    async def checker(token: TokenDep) -> bool:
        has_access = await check_benefit(benefit_code, token)
        
        if not has_access:
            # 获取当前用户等级（如果可能）
            current_level = None
            try:
                benefits_data = await get_member_benefits(token)
                current_level = benefits_data.get("level_name")
            except:
                pass
            
            raise_benefit_required(benefit_code, current_level)
        
        return True
    
    return checker


async def check_feature_permission(feature: str, token: TokenDep) -> bool:
    """
    [已弃用] 请使用 check_benefit
    检查会员是否有特定订阅功能权限
    """
    return await check_benefit(feature, token)


def require_subscription_feature(feature: str):
    """
    [已弃用] 请使用 require_benefit
    FastAPI 依赖工厂：要求特定订阅功能权限
    """
    return require_benefit(feature)


# AI Quota management is now handled via the Go Gateway.
# The following helpers are deprecated and removed.


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
