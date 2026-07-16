import json
import time

import psutil
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.schemas.system import (
    CloudStatusResponse,
    EmbeddingApplyResponse,
    EmbeddingConfigRequest,
    EmbeddingTestResponse,
    HealthCheckResponse,
    LLMApplyResponse,
    LLMConfigRequest,
    LLMTestResponse,
    ModelsListResponse,
    SystemStatusResponse,
)
from app.infrastructure.config import EmbeddingConfigService
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm import LLMConfigService, LLMFactory
from app.infrastructure.llm.platform_service import (
    get_available_embedding_models,
    get_available_llm_models,
)
from app.models.system import SystemConfig

router = APIRouter(prefix="/system", tags=["system"])


from app.core.config import settings

@router.get("/status", dependencies=[Depends(get_current_user)])
def get_system_status() -> SystemStatusResponse:
    """
    Get real-time system CPU and RAM usage.
    """
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()

    return SystemStatusResponse(
        cpu_percent=cpu_percent,
        ram_percent=ram.percent,
        ram_used_gb=round(ram.used / (1024**3), 2),
        ram_total_gb=round(ram.total / (1024**3), 2),
        status="ok",
        enable_macro_self_healing=settings.ENABLE_MACRO_SELF_HEALING,
    )


@router.get("/config", dependencies=[Depends(get_current_user)])
def get_system_config() -> list[SystemConfig]:
    return SystemConfigService.get_all()


@router.get("/health")
def health_check() -> HealthCheckResponse:
    """
    Simple health check for startup probing.
    """
    return HealthCheckResponse(status="ok", service="evoloop-backend")


@router.post("/config", dependencies=[Depends(get_current_user)])
async def update_system_config(config: SystemConfig) -> SystemConfig:
    """Update system configuration and trigger side effects if needed."""
    return await SystemConfigService.set_value_async(config.key, config.value, config.description)


@router.post("/embedding/test", dependencies=[Depends(get_current_user)])
async def test_embedding_connection(req: EmbeddingConfigRequest) -> EmbeddingTestResponse:
    """
    Validate connection to embedding provider.
    """
    success, dim = await EmbeddingConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
    )
    return EmbeddingTestResponse(success=success, dimensions=dim)


@router.post("/embedding/apply", dependencies=[Depends(get_current_user)])
async def apply_embedding_config(req: EmbeddingConfigRequest) -> EmbeddingApplyResponse:
    """
    Apply new embedding config. THIS IS DESTRUCTIVE (Resets Vector DB).
    """
    await EmbeddingConfigService.switch_embedding_model(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
        dimensions=req.dimensions,
        current_project_id=req.project_id,
    )

    # Save Custom Model Name (always save the model name provided in the config card)
    SystemConfigService.set_value("CUSTOM_EMBEDDING_MODEL", req.model)

    # Save Default Model ID for Embedding
    default_id = req.default_model_id or req.model
    if not default_id.startswith("embedding-"):
        # Auto-prefix platform models if needed, but usually frontend sends the ID
        pass

    SystemConfigService.set_value("EMBEDDING_MODEL", default_id)
    return EmbeddingApplyResponse(
        status="applied",
        message="Embedding model switched. Re-indexing triggered.",
    )


# --- LLM Config ---

@router.post("/llm/test", dependencies=[Depends(get_current_user)])
async def test_llm_connection(req: LLMConfigRequest) -> LLMTestResponse:
    """
    Validate connection to LLM provider.
    """
    success, reply = await LLMConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
        headers=req.headers,
    )
    return LLMTestResponse(success=success, reply=reply)


@router.post("/llm/apply", dependencies=[Depends(get_current_user)])
async def apply_llm_config(req: LLMConfigRequest) -> LLMApplyResponse:
    """
    Apply new LLM config.
    """
    # Determine config type based on whether a custom base URL is provided
    config_type = "custom" if req.base_url else "platform"
    SystemConfigService.set_value("LLM_CONFIG_TYPE", config_type)

    # Save provider details (used for Custom mode)
    SystemConfigService.set_value("LLM_PROVIDER", req.provider)
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", req.provider_type)
    SystemConfigService.set_value("LLM_BASE_URL", req.base_url or "")

    # Save the Default Model ID
    default_id = req.default_model_id or req.model
    SystemConfigService.set_value("LLM_MODEL", default_id)

    if req.vision_model:
        SystemConfigService.set_value("VISION_MODEL", req.vision_model)
    if req.vision_base_url:
        SystemConfigService.set_value("VISION_BASE_URL", req.vision_base_url)
    if req.vision_api_key:
        SystemConfigService.set_value("VISION_API_KEY", req.vision_api_key)
    if req.vision_provider_type:
        SystemConfigService.set_value("VISION_PROVIDER_TYPE", req.vision_provider_type)
    if req.api_key:
        SystemConfigService.set_value("LLM_API_KEY", req.api_key)

    # Save Custom Model Name (always save the model name provided in the config card)
    SystemConfigService.set_value("CUSTOM_LLM_MODEL", req.model)

    # Save Custom HTTP Headers
    headers_str = json.dumps(req.headers) if req.headers else "{}"
    SystemConfigService.set_value("LLM_HEADERS", headers_str)

    # Clear LLM Factory cache
    LLMFactory.clear_cache()

    return LLMApplyResponse(status="applied", message="LLM Configuration applied successfully.")


@router.get("/cloud-status")
async def get_cloud_status() -> CloudStatusResponse:
    """
    Debug endpoint to check EvoCloud connection status.
    """
    from app.core.evocloud import evocloud_manager

    token = await evocloud_manager.get_token()
    return CloudStatusResponse(
        is_logged_in=bool(token),
        device_key=evocloud_manager.link.device_key if evocloud_manager.link else None,
        is_linked=evocloud_manager.link.is_connected() if evocloud_manager.link else False,
        device_name=evocloud_manager.link.device_name if evocloud_manager.link else "Unknown",
        api_url=evocloud_manager.api.base_url if evocloud_manager.api else "Unknown",
    )


@router.get("/llm/models")
async def get_llm_models(config_type: str = None) -> ModelsListResponse:
    """
    获取可用的 LLM 模型列表

    Args:
        config_type: 配置类型过滤 (platform/custom)
                    platform - 只返回平台提供的模型
                    custom - 只返回自定义模型
                    不传则根据系统配置自动过滤

    返回:
        符合条件的模型列表
    """
    models = await get_available_llm_models(config_type=config_type)
    return ModelsListResponse(models=models, last_updated=time.strftime("%Y-%m-%d"))


@router.get("/embedding/models")
async def get_embedding_models() -> ModelsListResponse:
    """
    获取可用的 Embedding 模型列表（包含平台模型和自定义模型）
    """
    models = await get_available_embedding_models()
    return ModelsListResponse(models=models, last_updated=time.strftime("%Y-%m-%d"))

