import logging
from collections.abc import Generator
from datetime import datetime
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.evocloud import evocloud_manager
from app.models import User

logger = logging.getLogger(__name__)


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
        # Pass the token directly to Member Center API via unified client
        result = await evocloud_manager.api.get_user_info(token)

        if result.get("code") != 0:
            # Map error
            error_msg = result.get("message", "Validation failed")
            if "token" in error_msg.lower() or result.get("code") in [-1, 401]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token or expired session",
                )
            raise HTTPException(status_code=400, detail=error_msg)

        user_data = result.get("data", {})

        if user_data:
            user_data["id"] = user_data.get("member_id")

        # Map Member Center data to User model
        user = User.model_validate(user_data)

        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")

        return user
    except HTTPException as e:
        raise e
    except Exception as e:
        # Log error here if logger is available
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(token: TokenDepOptional) -> User | None:
    if not token:
        return None
    try:
        result = await evocloud_manager.api.get_user_info(token)

        if result.get("code") != 0:
            return None

        user_data = result.get("data", {})
        if user_data:
            user_data["id"] = user_data.get("member_id")

        user = User.model_validate(user_data)
        if not user.is_active:
            return None
        return user
    except Exception:
        return None


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


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
    If still no user, 'x_guest_id' is checked against Redis daily limits.
    """
    # 0. Backfill User from Query Token if Header Auth missing
    if not current_user and token:
        try:
            # We must import inside function to avoid circular imports layout if any,
            # though get_current_user_optional imports it too.
            result = await evocloud_manager.api.get_user_info(token)
            if result.get("code") == 0:
                user_data = result.get("data", {})
                if user_data:
                    # It's a valid user, so we consider them authenticated.
                    # We don't strictly need to construct the User object unless downstream needs it,
                    # but this function just returns None on success.
                    return
        except Exception:
            # Token invalid, fall through to guest check
            pass

    if current_user:
        return

    # Resolve IDs
    effective_guest_id = x_guest_id or guest_id

    if not effective_guest_id:
        raise HTTPException(status_code=401, detail="Authentication required (or guest_id)")

    # Check Guest Limits via Redis
    try:
        redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

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
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"guest:usage:{today}:{effective_guest_id}"

        async with redis_client:
            current_usage = await redis_client.incr(key)
            if current_usage == 1:
                await redis_client.expire(key, 86400)  # 24h

        if current_usage > limit:
            raise HTTPException(
                status_code=402,
                detail=f"Guest limit reached ({limit}/day). Please upgrade.",
            )

        # logger.info(f"Guest {effective_guest_id} usage: {current_usage}/{limit}")

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Redis error during guest check: {e}")
        # Fail-Close: If Redis is down, we cannot verify quota, so we must deny to prevent abuse.
        raise HTTPException(status_code=503, detail="Guest validation service temporary unavailable.")
