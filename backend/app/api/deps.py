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
from app.infrastructure.database.redis import redis_client
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

        # 2. Try Redis Cache first
        user_data = None
        try:
            cached_data = await redis_client.get(f"evoloop:user:{member_id}")
            if cached_data:
                user_data = json.loads(cached_data)
        except Exception as e:
            logger.debug(f"Redis cache miss/error: {e}")

        # 3. Fallback to Cloud fetch if cache miss
        if not user_data:
            cloud_token = identity_service.get_cloud_token()
            if not cloud_token:
                 raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No cloud credentials found")

            result = await evocloud_manager.api.get_user_info(cloud_token)
            if result.get("code") != 0:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cloud verification failed")

            user_data = result.get("data", {})
            # Cache it back to Redis
            try:
                await redis_client.set(f"evoloop:user:{member_id}", json.dumps(user_data), ex=86400)
            except Exception:
                pass

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

    # Check Guest Limits via Redis
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
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"guest:usage:{today}:{effective_guest_id}"

        current_usage = await redis_client.incr(key)
        if current_usage == 1:
            await redis_client.expire(key, 86400)  # 24h

        if current_usage > limit:
            raise HTTPException(
                status_code=402,
                detail=f"Guest limit reached ({limit}/day). Please upgrade.",
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Redis error during guest check: {e}")
        # Fail-Close: If Redis is down, we cannot verify quota, so we must deny to prevent abuse.
        raise HTTPException(status_code=503, detail="Guest validation service temporary unavailable.")
