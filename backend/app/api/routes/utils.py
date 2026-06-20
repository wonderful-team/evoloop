from fastapi import APIRouter

from app.api.schemas.utils import EvoloopStatusResponse
from app.core.evocloud import evocloud_manager

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/evoloop-status")
async def get_evoloop_status() -> EvoloopStatusResponse:
    # Construct status from manager properties
    is_connected = evocloud_manager.link.is_connected() if evocloud_manager.link else False
    device_key = evocloud_manager.link.device_key if evocloud_manager.link else None
    device_name = evocloud_manager.link.device_name if evocloud_manager.link else "Unknown"

    return EvoloopStatusResponse(
        connected=is_connected,
        device_key=device_key,
        device_name=device_name,
    )


@router.get("/ai/config")
async def get_ai_config():
    """Get global AI config (Models, Prices)"""
    return {
        "code": 0,
        "data": {
            "models": [],
            "limits": {
                "guest_daily_limit": 10,
            },
        },
    }
