from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.external.imagicbox import imagicbox_client

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(req: LoginRequest):
    result = await imagicbox_client.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("message", "Login failed"))
    return result

@router.get("/status")
async def status():
    return imagicbox_client.get_status()

@router.post("/logout")
async def logout():
    await imagicbox_client.logout()
    
    # Clear Redis Token (Unified logic in client logout? No, client logout clears local state)
    # But for Redis (Server-side session-ish), let's keep it clean or move to client.
    # The client uses Redis for caching token? No, Client uses file.
    # Login route writes to Redis. Logout should clear Redis.
    try:
        from app.core.config import settings
        import redis.asyncio as redis
        redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        async with redis_client:
            await redis_client.delete("evoloop:link:token")
    except:
        pass

    return {"message": "Logged out"}
    
@router.get("/cancellation")
async def get_cancellation_info():
    """Get cancellation status and info"""
    return await imagicbox_client.get_cancellation_info()

@router.post("/cancellation")
async def apply_cancellation():
    """Apply for cancellation"""
    return await imagicbox_client.apply_cancellation()

@router.post("/cancellation/cancel")
async def cancel_cancellation_apply():
    """Cancel existing cancellation request"""
    return await imagicbox_client.cancel_cancellation_apply()
