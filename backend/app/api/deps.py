from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status, Header
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine

from app.models import User
from app.logging import logger

def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_db)]

async def get_token_header(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
         raise HTTPException(status_code=401, detail="Missing authorization header")
    if not authorization.startswith("Bearer "):
         raise HTTPException(status_code=401, detail="Invalid authorization header format")
    return authorization.split(" ")[1]

async def get_token_header_optional(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None  # Or raise error if strict
    return authorization.split(" ")[1]

TokenDep = Annotated[str, Depends(get_token_header)]
TokenDepOptional = Annotated[str | None, Depends(get_token_header_optional)]

async def get_current_user(token: TokenDep) -> User:
    try:
        from app.infrastructure.external.imagicbox import imagicbox_client
        
        # Pass the token directly to Member Center API via unified client
        result = await imagicbox_client.get_user_info(token)
        
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
        from app.infrastructure.external.imagicbox import imagicbox_client
        result = await imagicbox_client.get_user_info(token)
        
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

# --- Guest Verification Logic (Extracted from agent.py) ---
from datetime import datetime
import redis.asyncio as redis
from app.infrastructure.external.imagicbox import imagicbox_client

async def verify_guest_access(
    current_user: CurrentUserOptional,
    x_guest_id: Annotated[str | None, Header()] = None
) -> None:
    """
    Middleware-like dependency to verify guest access limits.
    If 'current_user' is present, this check is skipped (Paid/Auth user).
    If no user, 'x_guest_id' is checked against Redis daily limits.
    """
    if current_user:
        return

    if not x_guest_id:
        raise HTTPException(status_code=401, detail="Authentication required (or X-Guest-ID)")
    
    # Check Guest Limits via Redis
    try:
        redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        
        # 1. Get Global Config
        try:
            # Async call to global config
            config_res = await imagicbox_client.get_ai_global_config()
            limit = 10 # Default
            if config_res and config_res.get("code") == 0:
                limit = int(config_res.get("data", {}).get("guest_daily_limit", 10))
        except Exception as e:
            logger.warning(f"Failed to fetch guest config, using default: {e}")
            limit = 10
        
        if limit <= 0:
            raise HTTPException(status_code=403, detail="Guest chat disabled")

        # 2. Check Daily Usage
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"guest:usage:{today}:{x_guest_id}"
        
        async with redis_client:
            current_usage = await redis_client.incr(key)
            if current_usage == 1:
                await redis_client.expire(key, 86400) # 24h
        
        if current_usage > limit:
            raise HTTPException(
                status_code=402, 
                detail=f"Guest limit reached ({limit}/day). Please upgrade."
            )
            
        # logger.info(f"Guest {x_guest_id} usage: {current_usage}/{limit}")

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Redis error during guest check: {e}")
        # Fail-Close: If Redis is down, we cannot verify quota, so we must deny to prevent abuse.
        raise HTTPException(status_code=503, detail="Guest validation service temporary unavailable.")
