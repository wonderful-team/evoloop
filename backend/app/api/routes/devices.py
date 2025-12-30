from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.infrastructure.external.imagicbox import imagicbox_client

router = APIRouter()

# --- Schemas (Basic) ---
class SendCommandRequest(BaseModel):
    command_type: str
    params: dict = {}

@router.get("/")
async def get_devices(token: TokenDep):
    """List devices connected to account"""
    res = await imagicbox_client.get_devices()
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])

@router.post("/{device_id}/command")
async def send_command(device_id: int, req: SendCommandRequest, token: TokenDep):
    """Send remote command"""
    res = await imagicbox_client.send_command_to_device(device_id, req.dict())
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data")

@router.get("/{device_id}/logs")
async def get_recent_logs(
    device_id: int, 
    limit: int = 20, 
    project_id: Optional[int] = None,
    token: TokenDep = None
):
    """Get recent logs from device"""
    res = await imagicbox_client.get_device_logs(device_id, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])

@router.get("/{device_id}/logs/search")
async def search_logs(
    device_id: int, 
    query: str, 
    limit: int = 20, 
    project_id: Optional[int] = None,
    token: TokenDep = None
):
    """Search logs"""
    res = await imagicbox_client.search_device_logs(device_id, query, limit, project_id)
    if res.get("code") != 0:
        raise HTTPException(500, res.get("message"))
    return res.get("data", [])
