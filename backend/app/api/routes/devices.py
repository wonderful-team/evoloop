import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import TokenDep, require_benefit
from app.api.schemas.devices import BindResponse, DebugStatusResponse, BindClientRequest, SendCommandRequest
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def get_devices(token: TokenDep):
    """List devices connected to account (Cloud + Local ADB)"""
    # 1. Fetch Cloud Devices
    cloud_res = await evocloud_manager.api.get_devices(token=token)
    devices = []
    if cloud_res and cloud_res.get("code") == 0:
        # Gateway returns {"devices": [...], "total": N}
        data = cloud_res.get("data") or {}
        if isinstance(data, dict):
            devices = data.get("devices") or []
        elif isinstance(data, list):
            devices = data

        for d in devices:
            if isinstance(d, dict):
                d["connection_type"] = "cloud"
                d["status"] = "online"

    # 2. Fetch Local ADB Devices (from AwakenedState cache)
    try:
        from app.core.environment import get_awakened_state
        state = get_awakened_state()
        local_devices = state.android_devices if state else []
        
        for ld in local_devices:
            # Check if already in cloud list by serial/device_id
            exists = False
            for cd in devices:
                # Skip non-dict items
                if not isinstance(cd, dict):
                    continue
                # Some APIs use 'serial', some use 'device_id'. We check both.
                if str(cd.get("serial")) == ld.device_id or str(cd.get("id")) == ld.device_id:
                    cd["connection_type"] = "adb"
                    cd["status"] = "online"
                    cd["battery_percent"] = ld.battery_percent
                    exists = True
                    break
            
            if not exists:
                devices.append({
                    "id": ld.device_id,
                    "device_id": ld.device_id,
                    "serial": ld.device_id,
                    "model": ld.model,
                    "os_version": ld.os_version,
                    "status": "online" if ld.is_reachable else "offline",
                    "connection_type": "adb",
                    "battery_percent": ld.battery_percent
                })
    except Exception as e:
        logger.warning(f"Failed to merge local devices: {e}")

    return devices


@router.post("/{device_key}/command", dependencies=[Depends(require_benefit("mobile_control"))])
async def send_command(device_key: str, req: SendCommandRequest, token: TokenDep):
    """Send remote command"""
    res = await evocloud_manager.api.send_command_to_device(device_key, req.model_dump(), token=token)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data")


@router.get("/{device_key}/logs")
async def get_recent_logs(
    device_key: int,
    limit: int = 20,
    project_id: int | None = None,
    token: TokenDep = None,
):
    """Get recent logs from device"""
    res = await evocloud_manager.api.get_device_logs(device_key, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.get("/{device_key}/logs/search")
async def search_logs(
    device_key: str,
    query: str,
    limit: int = 20,
    project_id: int | None = None,
    token: TokenDep = None,
):
    """Search logs"""
    res = await evocloud_manager.api.search_device_logs(device_key, query, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.post("/{device_key}/bind", response_model=BindResponse)
async def bind_client(device_key: str, req: BindClientRequest, _token: TokenDep):
    """Bind mobile client to device"""
    # This notifies the cloud that a mobile client is interested in this device
    # Or specifically, it binds the client_id to the device in EvoCloud.
    res = await evocloud_manager.api.bind_client_id(device_key, req.client_id, token=_token)
    return BindResponse(status="success", data=res)


@router.post("/bind", response_model=BindResponse)
async def bind_current_device(req: BindClientRequest, _token: TokenDep):
    """Bind a client_id (e.g. mobile) to THIS server device"""
    if evocloud_manager.link.device_key:
        await evocloud_manager.link.bind_client_id(req.client_id)
        return BindResponse(status="success")
    return BindResponse(status="error", message="Device not registered on cloud")


@router.get("/debug/status", response_model=DebugStatusResponse)
async def get_debug_status(_token: TokenDep):
    """Debug endpoint to check EvoCloud client state"""
    token = await evocloud_manager.get_token()
    return DebugStatusResponse(
        token=token,
        is_logged_in=bool(token),
        token_prefix=(token[:10] + "...") if token else None,
        device_key=evocloud_manager.link.device_key if evocloud_manager.link else None,
        device_name=evocloud_manager.link.device_name if evocloud_manager.link else "Unknown",
        is_connected=evocloud_manager.link.is_connected() if evocloud_manager.link else False,
        api_url=evocloud_manager.api.base_url if evocloud_manager.api else "Unknown",
    )