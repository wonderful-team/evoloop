from fastapi import APIRouter
from pydantic import BaseModel

from app.core.evocloud import evocloud_manager

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


class EvoloopStatusResponse(BaseAPIResponse):
    connected: bool
    device_id: str | None = None
    device_name: str


@router.get("/evoloop-status")
async def get_evoloop_status() -> EvoloopStatusResponse:
    # Construct status from manager properties
    is_connected = evocloud_manager.link.is_connected() if evocloud_manager.link else False
    device_id = evocloud_manager.device_id
    device_name = evocloud_manager.link.device_name if evocloud_manager.link else "Unknown"

    return EvoloopStatusResponse(
        connected=is_connected,
        device_id=device_id,
        device_name=device_name,
    )


@router.get("/ai/config")
async def get_ai_config():
    """Get global AI config (Models, Prices)"""
    return await evocloud_manager.api.get_ai_global_config()
