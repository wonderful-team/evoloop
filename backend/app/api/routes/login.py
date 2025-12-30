from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import httpx

from app.core.config import settings
from app.models import Token
import asyncio
import redis.asyncio as redis

from app.infrastructure.evoloop_link.handler import handle_remote_command, handle_project_switch_event

router = APIRouter(tags=["login"])

@router.post("/login/access-token")
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    OAuth2 compatible token login, proxied to Member Center.
    """
    # Member Center Login API via Context Client
    from app.infrastructure.external.imagicbox import imagicbox_client
    
    # Try username/password login
    try:
        # 1. Config Handlers (Idempotent)
        imagicbox_client.set_command_handler(handle_remote_command)
        
        async def event_router(etype, edata):
            if etype == "project_switch":
                await handle_project_switch_event(edata)
        imagicbox_client.set_event_handler(event_router)

        # 2. Login (This triggers device link start if successful)
        result = await imagicbox_client.login(form_data.username, form_data.password)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Incorrect email or password"),
            )
        
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
        except:
             pass

        return Token(access_token=token_str, token_type="bearer")

    except Exception as e:
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise e
        print(f"ERROR: Login failed: {e}")
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
