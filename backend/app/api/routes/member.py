from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.external.imagicbox import imagicbox_client

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(req: LoginRequest):
    result = imagicbox_client.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("message", "Login failed"))
    return result

@router.get("/status")
async def status():
    return imagicbox_client.get_status()

@router.post("/logout")
async def logout():
    imagicbox_client.logout()
    
    # --- EvoLoop: Disconnect Device ---
    try:
        from app.infrastructure.evoloop_link.client import get_evoloop_client
        from app.logging import logger
        from app.core.config import settings
        import redis.asyncio as redis

        # 1. Stop Client
        client = get_evoloop_client()
        if client:
            client.stop()
            logger.info("[EvoLoop] Client stopped via logout.")
            
        # 2. Clear Redis Token
        try:
            redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            async with redis_client:
                await redis_client.delete("evoloop:link:token")
                logger.info("[EvoLoop] Token cleared from Redis via logout.")
        except Exception as e:
            logger.warning(f"[EvoLoop] Failed to clear token from Redis: {e}")
            
    except Exception as e:
        # Don't fail the logout response
        print(f"Error during EvoLoop logout: {e}")
    # ----------------------------------

    return {"message": "Logged out"}
    
@router.get("/cancellation")
async def get_cancellation_info():
    """Get cancellation status and info"""
    return imagicbox_client.get_cancellation_info()

@router.post("/cancellation")
async def apply_cancellation():
    """Apply for cancellation"""
    return imagicbox_client.apply_cancellation()

@router.post("/cancellation/cancel")
async def cancel_cancellation_apply():
    """Cancel existing cancellation request"""
    return imagicbox_client.cancel_cancellation_apply()
