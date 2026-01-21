from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.domain.system.embedding_config import EmbeddingConfigService
from app.domain.system.llm_config import LLMConfigService
from app.domain.system.service import SystemConfigService
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
def update_system_config(config: SystemConfig) -> SystemConfig:
    return SystemConfigService.set_value(config.key, config.value, config.description)


@router.get("/evolution-status", dependencies=[Depends(get_current_user)])
def get_evolution_status():
    from app.core.config import settings
    from app.domain.system.evolution_config import EvolutionConfigService
    from app.domain.system.service import SystemConfigService

    db_value = SystemConfigService.get_value(EvolutionConfigService.KEY, default="false")
    db_enabled = str(db_value).lower() == "true"

    # Optimization: Calculate effective status here instead of calling EvolutionConfigService.is_enabled()
    # which would trigger a second DB query.
    effective_enabled = settings.ENABLE_SELF_EVOLUTION and db_enabled

    return {
        "enabled": effective_enabled,
        "env_enabled": settings.ENABLE_SELF_EVOLUTION,
        "db_enabled": db_enabled,
    }


class EmbeddingConfigRequest(BaseModel):
    provider: str = Field(..., description="openai, ollama, or generic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
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
        current_project_id=req.project_id,
    )
    return {
        "status": "applied",
        "message": "Embedding model switched. Re-indexing triggered.",
    }


# --- LLM Config ---
class LLMConfigRequest(BaseModel):
    provider: str = Field(..., description="openai, anthropic, ollama, qwen_dashscope, generic")
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
    await LLMConfigService.applied_llm_config(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        vision_model=req.vision_model,
        api_key=req.api_key,
    )
    return {"status": "applied", "message": "LLM Configuration applied successfully."}


@router.post("/reset-knowledge", dependencies=[Depends(get_current_user)])
async def reset_knowledge_base():
    """
    [DANGER] Wipe the entire Knowledge Base (Neo4j + Postgres Index).
    """
    from app.domain.knowledge.maintenance import wipe_knowledge_base

    await wipe_knowledge_base()
    return {"status": "success", "message": "Knowledge Base Wiped."}
