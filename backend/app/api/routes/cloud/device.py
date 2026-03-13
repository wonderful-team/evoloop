"""
Cloud Device API - Device management and authentication.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Any

from app.api.deps import verify_device_token
from app.logging import logger

router = APIRouter()


class DeviceRegisterRequest(BaseModel):
    """Register a new client device."""
    device_name: str
    platform: str  # windows, macos, linux
    version: str
    hardware_id: str  # Unique hardware fingerprint


class DeviceRegisterResponse(BaseModel):
    """Device registration response."""
    device_id: str
    access_token: str
    refresh_token: str
    expires_in: int


class DeviceHeartbeat(BaseModel):
    """Device heartbeat with status."""
    device_id: str
    status: str  # online, busy, offline
    active_executions: int = 0
    local_skills_count: int = 0


@router.post("/register", response_model=DeviceRegisterResponse)
async def register_device(request: DeviceRegisterRequest) -> DeviceRegisterResponse:
    """
    Register a new EvoLoop client device.

    Returns device credentials for subsequent API calls.
    """
    logger.info(f"[CloudDevice] Register: {request.device_name} ({request.platform})")

    # TODO: Create device record in database
    return DeviceRegisterResponse(
        device_id="dev_001",
        access_token="eyJ...",
        refresh_token="rt...",
        expires_in=3600
    )


@router.post("/heartbeat")
async def device_heartbeat(
    data: DeviceHeartbeat,
    _: str = Depends(verify_device_token)
) -> dict[str, Any]:
    """
    Report device status to cloud.

    Cloud uses this for:
    - Device health monitoring
    - Load balancing
    - Push notifications
    """
    logger.debug(f"[CloudDevice] Heartbeat from {data.device_id}: {data.status}")

    return {
        "acknowledged": True,
        "server_time": "2024-01-15T10:00:00Z",
        "notifications": []  # Any pending messages for device
    }


@router.get("/{device_id}/status")
async def get_device_status(
    device_id: str,
    _: str = Depends(verify_device_token)
) -> dict[str, Any]:
    """Get current status of a device."""
    return {
        "device_id": device_id,
        "status": "online",
        "last_seen": "2024-01-15T10:00:00Z",
        "capabilities": ["android", "browser", "desktop"]
    }
