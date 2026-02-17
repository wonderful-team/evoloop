import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.core.evocloud.bridge.handlers import (
    handle_project_switch_event,
    handle_remote_command,
)
from app.core.identity import identity_service
from app.infrastructure.database.redis import redis_client
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
        
        # 2. Process login via IdentityService
        local_token = await identity_service.login_with_cloud_result(result)
        if not local_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize local session",
            )

        # 3. Persist cloud token to Redis for other services if needed (for now)
        user_data = result.get("data", {})
        member_id = result.get("member_id", 0)
        
        try:
            async with redis_client:
                await redis_client.set("evoloop:link:token", result.get("token"))
                # Store user info for fast access in deps.py
                if user_data and member_id is not None:
                    import json
                    await redis_client.set(f"evoloop:user:{member_id}", json.dumps(user_data), ex=86400)
        except Exception as e:
            logger.warning(f"Failed to cache user to Redis: {e}")
            pass

        return Token(access_token=local_token, token_type="bearer")

    except Exception as e:
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {e}",
        )

