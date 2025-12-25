from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/evoloop-status")
async def get_evoloop_status():
    from app.infrastructure.evoloop_link.client import get_evoloop_client
    client = get_evoloop_client()
    if not client:
        return {"connected": False, "reason": "No client modules initialized"}
    
    return {
        "connected": client._running and (client.ws is not None),
        "device_id": client.device_id,
        "device_name": client.device_name
    }
