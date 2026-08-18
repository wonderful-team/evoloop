import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.benefits import create_benefit_error_detail
from app.core.benefits.service import benefit_service
from app.core.config import settings
from app.core.identity import identity_service
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import User
from app.services.cache_services import RateLimitService

logger = logging.getLogger(__name__)


# ========== Cloud Device Authentication ==========


async def verify_device_token(
    authorization: str = Header(..., description="Bearer {device_token}"),
) -> str:
    """
    Verify device token for cloud API endpoints.

    TODO: Implement proper JWT validation with device registry
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization.replace("Bearer ", "")

    # TODO: Validate token against device registry
    # For now, accept any non-empty token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty device token"
        )

    return token


def extract_bearer_token(authorization: str | None) -> str | None:
    """
    Extract a bearer token from an Authorization header value.

    Returns ``None`` when the header is absent/empty. A non-bearer value is
    returned unchanged.
    """
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return authorization


def get_db() -> Generator[Session, None, None]:
    with Session(db_resource_manager.sync_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

# Global OAuth2 Scheme
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False
)

TokenDep = Annotated[str, Depends(oauth2_scheme)]
TokenDepOptional = Annotated[str | None, Depends(oauth2_scheme_optional)]


async def _get_authenticated_user(
    request: Request, token: str | None = None
) -> User | None:
    """
    Core authentication logic:
    1. Read member_id already resolved by ContextMiddleware from request.state (zero extra I/O).
    2. Fallback: resolve from token via IdentityService (hits Redis cache, not MC).
    3. Fallback: single-user mode stored session.
    """
    try:
        # 1. 优先复用 ContextMiddleware 已经解析并写入 request.state 的结果
        if token:
            resolved = getattr(request.state, "resolved_member_id", None)
            resolved_token = getattr(request.state, "resolved_token", None)
            if resolved is not None and resolved_token == token:
                return User(id=resolved, is_active=True)

            # 2. 未命中 state（不含中间件，例如直接调用时）：走 IdentityService（走 Redis 缓存）
            member_id = await identity_service.resolve_member_id_from_token(token)
            if member_id:
                return User(id=member_id, is_active=True)

        # 3. 回退：单用户模式（无 Header Token 场景）
        if not settings.MULTI_TENANT_MODE:
            member_id = await identity_service.get_member_id()
            if member_id:
                active_token = await identity_service.get_access_token()
                if active_token:
                    return User(id=member_id, is_active=True)

        return None
    except Exception as e:
        logger.error(f"Auth error during user resolution: {str(e)}", exc_info=True)
        return None


async def get_current_user(request: Request, token: TokenDepOptional = None) -> User:
    """
    Identify the current user. Raises 401 if not found.
    """
    user = await _get_authenticated_user(request, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    request: Request, token: TokenDepOptional = None
) -> User | None:
    """
    Get user if session or token is present, otherwise return None.
    """
    return await _get_authenticated_user(request, token)


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
        logger.exception(f"Benefit check failed [{benefit_code}]: {e}")
        return False


async def check_multiple_benefits(
    benefit_codes: list[str], token: TokenDep
) -> dict[str, bool]:
    """
    Check multiple benefits in one go (Thin Proxy).
    """
    member_id = await identity_service.resolve_member_id_from_token(token)
    if not member_id:
        return dict.fromkeys(benefit_codes, False)

    try:
        # For simplicity, we can fetch all entitlements once
        data = await benefit_service.get_member_entitlements(member_id)

        # Subscription expired: all benefits denied
        if data.get("is_expired", False):
            return dict.fromkeys(benefit_codes, False)

        benefits = data.get("benefits", {})

        result = {}
        for code in benefit_codes:
            # Check dict
            val = benefits.get(code, False)
            result[code] = (
                val
                if isinstance(val, bool)
                else (val > 0 if isinstance(val, int | float) else False)
            )
        return result
    except Exception as e:
        logger.exception(f"Batch benefit check failed: {e}")
        return dict.fromkeys(benefit_codes, False)


def raise_benefit_required(benefit_code: str, current_level: str | None = None):
    """
    抛出统一的权益不足异常
    """
    detail_model = create_benefit_error_detail(benefit_code, current_level)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=detail_model.model_dump()
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
                benefits_data = await benefit_service.get_member_entitlements(
                    member_id, token
                )
                current_level = benefits_data.get("level_name")
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

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
            logger.debug(f"Query token validation failed: {e}", exc_info=True)
            pass

    if current_user:
        return

    # Resolve IDs
    effective_guest_id = x_guest_id or guest_id

    if not effective_guest_id:
        raise HTTPException(
            status_code=401, detail="Authentication required (or guest_id)"
        )

    # Check Guest Limits via cache
    try:
        # 1. Guest daily limit (from settings, configurable via env)
        limit = settings.GUEST_DAILY_LIMIT

        if limit <= 0:
            raise HTTPException(status_code=403, detail="Guest chat disabled")

        # 2. Check Daily Usage
        rate_limit = RateLimitService()
        endpoint = "guest:usage"
        current_usage = await rate_limit.increment(
            endpoint,
            effective_guest_id,
            window=86400,  # 24h
        )

        if current_usage > limit:
            raise HTTPException(
                status_code=402,
                detail=f"Guest limit reached ({limit}/day). Please upgrade.",
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Cache error during guest check: {e}")
        # Fail-Close: If cache is down, we cannot verify quota, so we must deny to prevent abuse.
        raise HTTPException(
            status_code=503, detail="Guest validation service temporary unavailable."
        )
