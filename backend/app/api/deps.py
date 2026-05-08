import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import User
from app.services.benefit_service import benefit_service
from app.services.cache_services import RateLimitService

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
    with Session(db_resource_manager.sync_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

# Global OAuth2 Scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False)

TokenDep = Annotated[str, Depends(oauth2_scheme)]
TokenDepOptional = Annotated[str | None, Depends(oauth2_scheme_optional)]


async def _get_authenticated_user(token: str | None = None) -> User | None:
    """
    Core authentication logic:
    1. Check backend local session.
    2. Check provided token.
    """
    try:
        # 1. Try resolving from the backend's own session store first (Source of Truth)
        member_id = await identity_service.get_member_id()
        if member_id:
            active_token = await identity_service.get_access_token()
            if active_token:
                return User(id=member_id, is_active=True)

        # 2. Fallback to token from frontend (if backend store is empty)
        if token:
            member_id = await identity_service.resolve_member_id_from_token(token)
            if member_id:
                return User(id=member_id, is_active=True)

        return None
    except Exception as e:
        logger.error(f"Auth error during user resolution: {str(e)}", exc_info=True)
        return None


async def get_current_user(token: TokenDepOptional = None) -> User:
    """
    Identify the current user. Raises 401 if not found.
    """
    user = await _get_authenticated_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    token: TokenDepOptional = None
) -> User | None:
    """
    Get user if session or token is present, otherwise return None.
    """
    return await _get_authenticated_user(token)


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


# Fallback labels have been moved to the database (b2c_mall.member_privilege)
# and are now served dynamically via BenefitService.


async def check_benefit(benefit_code: str, token: TokenDep) -> bool:
    """
    Check if a member has a specific benefit/capability.
    Delegates to BenefitService which fetches data from Member Center.
    """
    try:
        member_id = await identity_service.resolve_member_id_from_token(token)
        if not member_id:
            return False

        return await benefit_service.has_benefit(member_id, benefit_code)
    except Exception as e:
        logger.error(f"Benefit check failed [{benefit_code}]: {e}")
        return False


async def check_multiple_benefits(benefit_codes: list[str], token: TokenDep) -> dict[str, bool]:
    """
    Check multiple benefits in one go (Thin Proxy).
    """
    member_id = await identity_service.resolve_member_id_from_token(token)
    if not member_id:
        return {code: False for code in benefit_codes}
        
    try:
        # For simplicity, we can fetch all entitlements once
        data = await benefit_service.get_member_entitlements(member_id)
        benefits = data.get("benefits", {})
        
        result = {}
        for code in benefit_codes:
            # Check dict
            val = benefits.get(code, False)
            result[code] = val if isinstance(val, bool) else (val > 0 if isinstance(val, int | float) else False)
        return result
    except Exception as e:
        logger.error(f"Batch benefit check failed: {e}")
        return {code: False for code in benefit_codes}


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
    """
    创建统一的权益错误详情
    """
    feature_name = benefit_service.get_benefit_label(benefit_code)
    return BenefitErrorDetail(
        feature=benefit_code,
        feature_name=feature_name,
        message=f"需要开通「{feature_name}」权益才能使用此功能",
        current_level=current_level or "免费用户",
    )


def raise_benefit_required(benefit_code: str, current_level: str | None = None):
    """
    抛出统一的权益不足异常
    """
    detail_model = create_benefit_error_detail(benefit_code, current_level)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail_model.model_dump()
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
                member_id = await identity_service.get_member_id(token)
                benefits_data = await benefit_service.get_member_entitlements(member_id, token)
                current_level = benefits_data.get("level_name")
            except Exception:
                pass
            
            raise_benefit_required(benefit_code, current_level)
        
        return True
    
    return checker


# AI Quota management is now handled via the Go Gateway.
# The following helpers are deprecated and removed.


# ==================== Guest Access ====================

async def verify_guest_access(
    current_user: CurrentUserOptional,
    x_guest_id: str | None = Header(None),
    guest_id: str | None = Query(None),
    token: str | None = Query(None),
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
            member_id = await identity_service.resolve_member_id_from_token(token)
            if member_id is not None:
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
