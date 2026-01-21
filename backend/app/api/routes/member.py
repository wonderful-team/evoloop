from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.infrastructure.external.evocloud import evocloud_client

router = APIRouter(tags=["member"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    result = await evocloud_client.login(req.username, req.password)
    if not result.get("success"):
        raise HTTPException(
            status_code=401, detail=result.get("message", "Login failed")
        )
    return result


@router.get("/status")
async def status():
    return evocloud_client.get_status()


@router.post("/logout")
async def logout():
    await evocloud_client.logout()

    # Clear Redis Token (Unified logic in client logout? No, client logout clears local state)
    # But for Redis (Server-side session-ish), let's keep it clean or move to client.
    # The client uses Redis for caching token? No, Client uses file.


@router.get("/cancellation/info")
async def get_cancellation_info(_token: TokenDep):
    return await evocloud_client.get_cancellation_info()


@router.post("/cancellation/apply")
async def apply_cancellation(_token: TokenDep):
    return await evocloud_client.apply_cancellation()


@router.post("/cancellation/cancel")
async def cancel_cancellation(_token: TokenDep):
    return await evocloud_client.cancel_cancellation_apply()
