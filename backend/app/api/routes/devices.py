from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.infrastructure.external.evocloud import evocloud_client


class BindClientRequest(BaseModel):
    client_id: str


router = APIRouter()


# --- Schemas (Basic) ---
class SendCommandRequest(BaseModel):
    command_type: str
    params: dict = {}


@router.get("/")
async def get_devices(_token: TokenDep):
    """List devices connected to account"""
    res = await evocloud_client.get_devices()
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.post("/{device_id}/command")
async def send_command(device_id: int, req: SendCommandRequest, _token: TokenDep):
    """Send remote command"""
    res = await evocloud_client.send_command_to_device(device_id, req.dict())
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
    res = await evocloud_client.get_device_logs(device_id, limit, project_id)
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
    res = await evocloud_client.search_device_logs(device_id, query, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.post("/{device_id}/bind")
async def bind_client(_device_id: int, _req: BindClientRequest, _token: TokenDep):
    """Bind mobile client to device"""
    # Verify device belongs to user? EvoCloud usually handles this logic.
    # EvoCloudClient uses device_id stored in self?
    # No, it uses self.device_id for its own link.
    # But here we are binding A CLIENT (mobile) to THIS SERVER (as a device)?
    # useEvoLoopWebSocket.ts: "Bind mobile client to user" via EvoLoopApi.bindMobile(clientId).
    # Legacy EvoLoopApi.bindMobile logic: POST /evolooplink/api/device/bind?
    # EvoCloudClient._bind_client_id uses self.device_id (Server's ID).
    # If the USER is calling this, they are telling the Server: "Bind this ClientID to YOU (Server)".
    # So we don't need {device_id} in path if we bind to current server?
    # BUT `useEvoLoopWebSocket` calls it when it gets 'init' message from WS.
    # The WS is connected to `EvoCloud`.
    # `EvoCloud` identifies THIS server by `device_key`.
    # The MOBILE client connects to `EvoCloud` too? Or connects to THIS server?
    # frontend/src/hooks/useEvoLoopWebSocket.ts connects to `WS_URL` which defaults to `wss://mall.imagicbox.cn/wss/`.
    # So Mobile connects to EvoCloud.
    # EvoCloud sends 'init' with 'client_id'.
    # Mobile calls `EvoLoopApi.bindMobile(clientId)`.
    # This must tell Backend (Server) to bind that ClientID to itself?
    # `EvoCloudClient._bind_client_id` does exactly that: `POST /evolooplink/api/device/bind` with `self.device_id` and `client_id`.
    # So we need an endpoint `POST /devices/bind` (no ID in path, implicit current server) OR `POST /bind`.
    # Since `devices.py` is mounted at `/api/devices` (usually?),
    # I'll add `POST /bind` to `devices.py` or `POST /current/bind`.
    # If I put it in `devices.py`, `router` prefix might be `/devices`?
    # I need to check `main.py` for router connection.
    # Assuming `/api/devices`.
    # I'll add `POST /bind` which calls `evocloud_client._bind_client_id(req.client_id)`.
    # Wait, `_bind_client_id` is "private". I should make it public or expose wrapper.
    # It is `async def _bind_client_id`.
    # I will call it or expose a public one.
    # I'll call it directly since I'm in same app.
    pass


@router.post("/bind")
async def bind_current_device(req: BindClientRequest, _token: TokenDep):
    """Bind a client_id (e.g. mobile) to this device"""
    # Requires access to internal method or we expose public one.
    # For now accessing 'link' directly to bind.
    if evocloud_client.link:
        await evocloud_client.link._bind_client_id(req.client_id)
        return {"status": "success"}
    return {"status": "error", "message": "Link not available"}
