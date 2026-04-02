import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.infrastructure.config import EmbeddingConfigService
from app.infrastructure.llm import LLMConfigService
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.platform_service import (
    get_available_llm_models,
    get_available_embedding_models,
)
from app.models.config import SystemConfig

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/config", dependencies=[Depends(get_current_user)])
def get_system_config() -> list[SystemConfig]:
    return SystemConfigService.get_all()


@router.get("/health")
def health_check():
    """
    Simple health check for startup probing.
    """
    return {"status": "ok", "service": "evoloop-backend"}


@router.post("/config", dependencies=[Depends(get_current_user)])
async def update_system_config(config: SystemConfig) -> SystemConfig:
    """Update system configuration and trigger side effects if needed."""
    return await SystemConfigService.set_value_async(config.key, config.value, config.description)


class EmbeddingConfigRequest(BaseModel):
    provider: str = Field(..., description="openai, ollama, or generic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
    dimensions: int | None = None  # Embedding dimensions
    api_key: str | None = None
    project_id: int | None = None  # For triggering reindex


@router.post("/embedding/test", dependencies=[Depends(get_current_user)])
async def test_embedding_connection(req: EmbeddingConfigRequest):
    """
    Validate connection to embedding provider.
    """
    success, dim = await EmbeddingConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
    )
    return {"success": success, "dimensions": dim}


@router.post("/embedding/apply", dependencies=[Depends(get_current_user)])
async def apply_embedding_config(req: EmbeddingConfigRequest):
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
    return {
        "status": "applied",
        "message": "Embedding model switched. Re-indexing triggered.",
    }


# --- LLM Config ---
class LLMConfigRequest(BaseModel):
    provider: str = Field(..., description="供应商名称: openai, anthropic, moonshot, deepseek")
    provider_type: str = Field(default="openai", description="协议类型: openai | anthropic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
    vision_model: str | None = Field(None, description="Vision Model Name (e.g. gpt-4o)")
    api_key: str | None = None


@router.post("/llm/test", dependencies=[Depends(get_current_user)])
async def test_llm_connection(req: LLMConfigRequest):
    """
    Validate connection to LLM provider.
    """
    success, reply = await LLMConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
    )
    return {"success": success, "reply": reply}


@router.post("/llm/apply", dependencies=[Depends(get_current_user)])
async def apply_llm_config(req: LLMConfigRequest):
    """
    Apply new LLM config.
    """
    # Save provider_type for Custom mode
    SystemConfigService.set_value("LLM_PROVIDER", req.provider)
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", req.provider_type)
    SystemConfigService.set_value("LLM_BASE_URL", req.base_url)
    SystemConfigService.set_value("LLM_MODEL", req.model)

    if req.vision_model:
        SystemConfigService.set_value("VISION_MODEL", req.vision_model)
    if req.api_key:
        SystemConfigService.set_value("LLM_API_KEY", req.api_key)

    # Clear LLM Factory cache
    from app.infrastructure.llm.factory import LLMFactory
    LLMFactory.clear_cache()

    return {"status": "applied", "message": "LLM Configuration applied successfully."}


@router.post("/reset-knowledge", dependencies=[Depends(get_current_user)])
async def reset_knowledge_base():
    """
    [DANGER] Wipe the entire Knowledge Base (Neo4j + Postgres Index).
    """
    from app.domain.knowledge.maintenance import wipe_knowledge_base

    await wipe_knowledge_base()
    return {"status": "success", "message": "Knowledge Base Wiped."}


@router.get("/cloud-status")
async def get_cloud_status():
    """
    Debug endpoint to check EvoCloud connection status.
    """
    from app.core.evocloud import evocloud_manager

    return {
        "is_logged_in": bool(evocloud_manager.get_token()),
        "device_id": evocloud_manager.device_id,
        "is_linked": evocloud_manager.link.is_connected() if evocloud_manager.link else False,
        "device_name": evocloud_manager.link.device_name if evocloud_manager.link else "Unknown",
        "api_url": evocloud_manager.api.base_url if evocloud_manager.api else "Unknown"
    }


@router.get("/llm/models")
async def get_llm_models(config_type: str = None):
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
    return {
        "models": models,
        "last_updated": time.strftime("%Y-%m-%d")
    }


@router.get("/embedding/models")
async def get_embedding_models():
    """
    获取可用的 Embedding 模型列表（包含平台模型和自定义模型）
    """
    models = await get_available_embedding_models()
    return {
        "models": models,
        "last_updated": time.strftime("%Y-%m-%d")
    }
