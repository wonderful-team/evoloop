import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import TokenDep, require_benefit
from app.api.schemas.devices import (
    BindClientRequest,
    BindResponse,
    DebugStatusResponse,
    SendCommandRequest,
)
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
    """Send remote command."""
    cmd_data = req.model_dump()

    # Build canonical command body expected by the Gateway.
    content = cmd_data.pop("content", None) or cmd_data.pop("params", {}) or {}
    command_type = cmd_data.pop("command_type", "relay")
    body = {"action": command_type, "content": content, **cmd_data}

    # Map API command_type to canonical envelope type.
    # 通用指令统一走 command.relay，由接收端按 body.action 分发（与 Mobile 端
    # conversations.ts 的 memory_add/update/delete 发送格式一致）。仅 gateway
    # 有专门 handler 的类型（stop/retry/rewind/hitl.response/hitl.cancel）需要
    # 显式映射；memory.sync / message.sync 是 Agent 主动推送数据快照的类型，
    # 不能用作指令（接收端 subscribers 只处理 command.relay/retry/rewind）。
    envelope_type_map = {
        "stop": "command.stop",
        "retry": "command.retry",
        "rewind": "command.rewind",
        "hitl_response": "hitl.response",
        "hitl_cancel": "hitl.cancel",
    }
    envelope_type = envelope_type_map.get(command_type, "command.relay")

    res = await evocloud_manager.api.send_command_to_device(device_key, body, token=token, envelope_type=envelope_type)
    code = res.get("code")
    message = res.get("message", "")
    if code != 0:
        status_code = 500
        if code == 404 or "device not found" in message.lower():
            status_code = 404
        raise HTTPException(status_code, message)
    return res.get("data")


@router.get("/{device_key}/logs")
async def get_recent_logs(
    device_key: str,
    _token: TokenDep,
    limit: int = 20,
    project_id: int | None = None,
):
    """Get recent logs from device"""
    res = await evocloud_manager.api.get_device_logs(device_key, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])


@router.get("/{device_key}/logs/search")
async def search_logs(
    device_key: str,
    _token: TokenDep,
    query: str,
    limit: int = 20,
    project_id: int | None = None,
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
    link = evocloud_manager.link if evocloud_manager else None
    return DebugStatusResponse(
        is_logged_in=bool(token),
        token_prefix=(token[:10] + "...") if token else None,
        device_id=link.device_key if link else None,
        device_name=link.device_name if link else "Unknown",
        is_connected=link.is_connected() if link else False,
        api_url=evocloud_manager.api.base_url if evocloud_manager.api else "Unknown",
    )
