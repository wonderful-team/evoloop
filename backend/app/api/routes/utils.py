from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/evoloop-status")
async def get_evoloop_status():
    from app.infrastructure.external.imagicbox import imagicbox_client
    status = imagicbox_client.get_status()
    
    return {
        "connected": status.get("device_connected", False),
        "device_id": status.get("device_id"),
        "device_name": imagicbox_client.device_name # Access prop directly
    }
