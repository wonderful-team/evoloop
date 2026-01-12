from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/evoloop-status")
async def get_evoloop_status():
    from app.infrastructure.external.evocloud import evocloud_client
    status = evocloud_client.get_status()

    return {
        "connected": status.get("device_connected", False),
        "device_id": status.get("device_id"),
        "device_name": evocloud_client.device_name # Access prop directly
    }


@router.get("/ai/config")
async def get_ai_config():
    """Get global AI config (Models, Prices)"""
    from app.infrastructure.external.evocloud import evocloud_client
    return await evocloud_client.get_ai_global_config()
