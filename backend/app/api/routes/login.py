import logging
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.core.evocloud.bridge.handlers import (
    handle_project_switch_event,
    handle_remote_command,
)
from app.utils.security import create_access_token

from app.models import Token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["login"])


@router.post("/login/access-token", response_model=Token)
async def login_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    OAuth2 compatible token login, get an access token for future requests.
    Also logs into EvoLoop Cloud.
    """
    try:
        # 1. Login to EvoLoop Cloud
        # Handlers should already be set by main.py, but we can ensure it here or if main startup failed to auth.
        evocloud_manager.set_command_handler(handle_remote_command)

        async def event_router(etype, edata):
            if etype == "project_switch":
                await handle_project_switch_event(edata)

        evocloud_manager.set_event_handler(event_router)

        result = await evocloud_manager.login(form_data.username, form_data.password)

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Incorrect email or password"),
            )

        user_data = result.get("data", {}) # or check structure of result
        # API might return {"success": True, "token": ...} or the full response.
        # Base on `http_client.py` implementation: return {"success": True, "token": token}
        
        # We might need to verify the return shape from `http_client.login`. 
        # It returns {"success": True, "token": token}
        
        token_str = result.get("token")
        if not token_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token not found in response",
            )

        # Persist token to Redis for other services if needed
        try:
            redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            async with redis_client:
                await redis_client.set("evoloop:link:token", token_str)
        except Exception:
            pass

        return Token(access_token=token_str, token_type="bearer")

    except Exception as e:
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {e}",
        )

    # Note: The return above exits the function. We need to insert logic BEFORE return.
    # But since we're replacing the whole block or appended logic, let's restructure slightly or just paste imports and func.
    # Actually, the tool allows replacing the whole file content or chunks.
    # It's cleaner to rewrite the function or use a helper.
    # Due to complexity of inserting imports at top and code at bottom, I'll do this in two steps or careful chunking.
    # Step 1: Add imports.
    # Step 2: Add logic before return.

    # Wait, I can't do two writes in one step easily if they are far apart.
    # Let's do imports first.
