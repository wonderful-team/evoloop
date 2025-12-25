from fastapi import APIRouter, Depends
from app.domain.system.service import SystemConfigService
from app.models.config import SystemConfig
from app.api.deps import get_current_user

router = APIRouter(prefix="/system", tags=["system"])

@router.get("/config", dependencies=[Depends(get_current_user)])
def get_system_config() -> list[SystemConfig]:
    return SystemConfigService.get_all()

@router.post("/config", dependencies=[Depends(get_current_user)])
def update_system_config(config: SystemConfig) -> SystemConfig:
    return SystemConfigService.set_value(config.key, config.value, config.description)
