from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.core.evocloud import evocloud_manager


class BindClientRequest(BaseModel):
    client_id: str


router = APIRouter()


# --- Schemas (Basic) ---
class SendCommandRequest(BaseModel):
    command_type: str
    params: dict = {}


@router.get("/")
async def get_devices(token: TokenDep):
    """List devices connected to account"""
    res = await evocloud_manager.api.get_devices(token=token)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.post("/{device_id}/command")
async def send_command(device_id: int, req: SendCommandRequest, token: TokenDep):
    """Send remote command"""
    res = await evocloud_manager.api.send_command_to_device(device_id, req.dict(), token=token)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data")


@router.get("/{device_id}/logs")
async def get_recent_logs(
    device_id: int,
    limit: int = 20,
    project_id: int | None = None,
    token: TokenDep = None,
):
    """Get recent logs from device"""
    res = await evocloud_manager.api.get_device_logs(device_id, limit, project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.get("/{device_id}/logs/search")
async def search_logs(
    device_id: int,
    query: str,
    limit: int = 20,
    project_id: int | None = None,
    token: TokenDep = None,
):
    """Search logs"""
    res = await evocloud_manager.api.search_device_logs(device_id, query, limit, project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.post("/{device_id}/bind")
async def bind_client(device_id: int, req: BindClientRequest, _token: TokenDep):
    """Bind mobile client to device"""
    # This notifies the cloud that a mobile client is interested in this device
    # Or specifically, it binds the client_id to the device in EvoCloud.
    res = await evocloud_manager.api.bind_client_id(device_id, req.client_id)
    return {"status": "success", "data": res}


@router.post("/bind")
async def bind_current_device(req: BindClientRequest, _token: TokenDep):
    """Bind a client_id (e.g. mobile) to THIS server device"""
    if evocloud_manager.device_id:
        await evocloud_manager.link._bind_client_id(req.client_id)
        return {"status": "success"}
    return {"status": "error", "message": "Device not registered on cloud"}


@router.get("/debug/status")
async def get_debug_status(_token: TokenDep):
    """Debug endpoint to check EvoCloud client state"""
    return {
        "is_logged_in": bool(evocloud_manager.get_token()),
        "token_prefix": (evocloud_manager.get_token()[:10] + "...") if evocloud_manager.get_token() else None,
        "device_id": evocloud_manager.device_id,
        "device_name": evocloud_manager.link.device_name if evocloud_manager.link else "Unknown",
        "is_connected": evocloud_manager.link.is_connected() if evocloud_manager.link else False,
        "api_url": evocloud_manager.api.base_url if evocloud_manager.api else "Unknown",
    }
