from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import httpx

from app.core.config import settings
from app.models import Token
import asyncio
import redis.asyncio as redis
from app.infrastructure.evoloop_link.client import init_evoloop_client, set_evoloop_client, get_evoloop_client
from app.infrastructure.evoloop_link.handler import handle_remote_command, handle_project_switch_event

router = APIRouter(tags=["login"])

@router.post("/login/access-token")
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    OAuth2 compatible token login, proxied to Member Center.
    """
    # Member Center Login API (Assuming standard Niushop V5/V6 or provided structure)
    # Typically: POST /api/login/login (or similar)
    # We need to adapt the form_data (username, password) to Member Center's expected format.
    
    base_url = str(settings.IMAGICBOX_API_URL).rstrip('/')
    
    # Try username/password login
    try:
        async with httpx.AsyncClient() as client:
            # Different systems have different login endpoints. 
            # Adjusting for common Niushop patterns: /api/login/login
            response = await client.post(
                f"{base_url}/api/login/login",
                json={
                    "username": form_data.username,
                    "password": form_data.password,
                    # Some systems need 'account' instead of 'username'
                },
                timeout=10.0
            )
            
            # If standard login fails, try alias or different structure if needed.
            # For now assuming this structure.
            
            print(f"DEBUG: Member Center Response Status: {response.status_code}")
            print(f"DEBUG: Member Center Response Body: {response.text}")
            
            if response.status_code != 200:
                print(f"ERROR: Upstream returned {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Incorrect email or password",
                )
            
            data = response.json()
            
            # Check business code
            # Niushop success code is >= 0 (usually 0 or 1)
            if data.get("code", -1) < 0:
                print(f"ERROR: Upstream business code error: {data}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=data.get("message", "Login failed"),
                )
                
            # Extract token. Structure depends on Member Center response.
            # Assuming data['data']['token'] exists.
            token_str = data.get("data", {}).get("token")
            if not token_str:
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Token not found in response",
                )
            
            # --- EvoLoop Link: Auto Start Client ---
            try:
                # 1. Persist token to Redis
                redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
                async with redis_client:
                    await redis_client.set("evoloop:link:token", token_str)
                
                # 2. Check if client is running, if not start it
                current_client = get_evoloop_client()
                # If no client or client stopped, (re)start. 
                # Note: If token changed, we might want to restart anyway? 
                # For simplicity, if not running or token changed (future optimization), just start.
                if not current_client or not current_client._running:
                    print("[EvoLoop] Starting Link Client after login...")
                    evoloop_client = init_evoloop_client(
                        token=token_str,
                        device_name=settings.EVOLOOP_DEVICE_NAME
                    )
                    set_evoloop_client(evoloop_client)
                    evoloop_client.set_command_handler(handle_remote_command)
                    
                    async def event_router(etype, edata):
                        if etype == "project_switch":
                            await handle_project_switch_event(edata)
                    evoloop_client.set_event_handler(event_router)

                    if settings.EVOLOOP_LINK_BASE_URL:
                        evoloop_client.base_url = settings.EVOLOOP_LINK_BASE_URL.rstrip("/")
                    if settings.EVOLOOP_LINK_WS_URL:
                        evoloop_client.ws_url = settings.EVOLOOP_LINK_WS_URL
                    
                    asyncio.create_task(evoloop_client.start())
                else:
                    print("[EvoLoop] Link Client already running.")

            except Exception as e:
                print(f"[EvoLoop] Auto-start failed: {e}")
            # --- End EvoLoop Link ---

            return Token(access_token=token_str, token_type="bearer")

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to connect to Member Center: {exc}",
        )
    except Exception as e:
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise e
        print(f"ERROR: Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )
    finally:
        # After successful token retrieval (logic inside try, but we can do it after success check)
        pass

    # Note: The return above exits the function. We need to insert logic BEFORE return.
    # But since we're replacing the whole block or appended logic, let's restructure slightly or just paste imports and func.
    # Actually, the tool allows replacing the whole file content or chunks.
    # It's cleaner to rewrite the function or use a helper.
    # Due to complexity of inserting imports at top and code at bottom, I'll do this in two steps or careful chunking.
    # Step 1: Add imports.
    # Step 2: Add logic before return.

    # Wait, I can't do two writes in one step easily if they are far apart.
    # Let's do imports first.
