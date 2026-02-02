from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.core.evocloud import evocloud_manager

router = APIRouter(tags=["member"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    result = await evocloud_manager.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(
            status_code=401, detail=result.get("message", "Login failed")
        )
    return result


@router.get("/status")
async def status():
    # Return basic status
    return {
        "is_logged_in": bool(evocloud_manager.get_token()),
        "device_id": evocloud_manager.device_id,
        "is_connected": evocloud_manager.link.is_connected() if evocloud_manager.link else False
    }


@router.post("/logout")
async def logout():
    # Logout logic: Clear token and stop link
    if evocloud_manager.api:
        evocloud_manager.api.set_token(None)
    if evocloud_manager.link:
        await evocloud_manager.link.stop()

    # Clear Redis Token (Unified logic in client logout? No, client logout clears local state)
    # But for Redis (Server-side session-ish), let's keep it clean or move to client.
    # The client uses Redis for caching token? No, Client uses file.


@router.get("/cancellation/info")
async def get_cancellation_info(_token: TokenDep):
    return await evocloud_manager.api.get_cancellation_info()


@router.post("/cancellation/apply")
async def apply_cancellation(_token: TokenDep):
    return await evocloud_manager.api.apply_cancellation()


@router.post("/cancellation/cancel")
async def cancel_cancellation(_token: TokenDep):
    return await evocloud_manager.api.cancel_cancellation_apply()
