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

from pydantic import BaseModel, Field
from typing import Optional
from app.domain.system.embedding_config import EmbeddingConfigService

class EmbeddingConfigRequest(BaseModel):
    provider: str = Field(..., description="openai, ollama, or generic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
    api_key: Optional[str] = None
    project_id: Optional[int] = None # For triggering reindex

@router.post("/embedding/test", dependencies=[Depends(get_current_user)])
async def test_embedding_connection(req: EmbeddingConfigRequest):
    """
    Validate connection to embedding provider.
    """
    success, dim = await EmbeddingConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key
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
        current_project_id=req.project_id
    )
    return {"status": "applied", "message": "Embedding model switched. Re-indexing triggered."}

# --- LLM Config ---
class LLMConfigRequest(BaseModel):
    provider: str = Field(..., description="openai, anthropic, ollama, qwen_dashscope, generic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
    api_key: Optional[str] = None

@router.post("/llm/test", dependencies=[Depends(get_current_user)])
async def test_llm_connection(req: LLMConfigRequest):
    """
    Validate connection to LLM provider.
    """
    from app.domain.system.llm_config import LLMConfigService
    success, reply = await LLMConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key
    )
    return {"success": success, "reply": reply}

@router.post("/llm/apply", dependencies=[Depends(get_current_user)])
async def apply_llm_config(req: LLMConfigRequest):
    """
    Apply new LLM config.
    """
    from app.domain.system.llm_config import LLMConfigService
    await LLMConfigService.applied_llm_config(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key
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
