"""API schemas for system routes."""

from typing import Any

from pydantic import Field

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest


class EmbeddingConfigRequest(ScopedRequest):
    provider: str = Field(..., description="openai, ollama, or generic")
    base_url: str = Field(..., description="API Base URL")
    model: str = Field(..., description="Model Name")
    dimensions: int | None = None
    api_key: str | None = None
    project_id: int | None = None


class SystemStatusResponse(BaseAPIResponse):
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    status: str = "ok"
    enable_macro_self_healing: bool = True


class HealthCheckResponse(BaseAPIResponse):
    status: str
    service: str


class EmbeddingTestResponse(BaseAPIResponse):
    dimensions: int | None = None


class EmbeddingApplyResponse(BaseAPIResponse):
    status: str


class LLMTestResponse(BaseAPIResponse):
    reply: str | None = None


class LLMApplyResponse(BaseAPIResponse):
    status: str


class CloudStatusResponse(BaseAPIResponse):
    is_logged_in: bool
    device_key: str | None = None
    is_linked: bool
    device_name: str
    api_url: str


class ModelsListResponse(BaseAPIResponse):
    models: list[dict[str, Any]]
    last_updated: str


class LLMConfigRequest(DynamicBaseModel):
    provider: str = Field(..., description="供应商名称: openai, anthropic, moonshot, deepseek")
    provider_type: str = Field(default="openai", description="协议类型: openai | anthropic")
    base_url: str | None = Field(None, description="API Base URL")
    model: str = Field(..., description="Model Name")
    vision_model: str | None = Field(None, description="Vision Model Name (e.g. gpt-4o)")
    vision_base_url: str | None = Field(None, description="独立 Vision API Base URL (本地 VLM)")
    vision_api_key: str | None = Field(None, description="独立 Vision API Key")
    vision_provider_type: str | None = Field(None, description="独立 Vision 协议类型: openai | anthropic")
    api_key: str | None = None
    headers: dict[str, str] | None = Field(None, description="自定义请求头 (JSON 字典)")


# --- Embedding Channel Schemas (independent tier chain) ---


class EmbeddingTierConfigRequest(DynamicBaseModel):
    tiers: str = Field(default="gguf,local,remote", description="Comma-separated tier priority")
    gguf_model: str | None = Field(None, description="Tier 1: GGUF file path")
    local_url: str | None = Field(None, description="Tier 2: Local HTTP URL")
    local_api_key: str | None = Field(None, description="Tier 2: API key")
    local_model: str | None = Field(None, description="Tier 2: model name")
    provider: str | None = Field(None, description="Tier 3: provider type (openai/ollama/lm-studio)")
    base_url: str | None = Field(None, description="Tier 3: API base URL")
    model: str | None = Field(None, description="Tier 3: model name")
    api_key: str | None = Field(None, description="Tier 3: API key")
    dimensions: int | None = Field(None, description="Tier 3: embedding dimensions")


class EmbeddingTierStatusResponse(BaseAPIResponse):
    active_tier: str | None = None
    gguf_available: bool = False
    local_available: bool = False
    remote_available: bool = False
    tiers: str = "gguf,local,remote"


class EmbeddingTierTestResponse(BaseAPIResponse):
    success: bool = False
    dimensions: int | None = None
    error: str | None = None


class DiscoveredModelResponse(DynamicBaseModel):
    id: str
    name: str
    source: str
    model_name: str
    base_url: str | None = None
    capabilities: list[str] = ["chat"]
    status: str = "unknown"
    context_window: int | None = None
    error: str | None = None


class ModelDiscoveryResponse(BaseAPIResponse):
    models: list[DiscoveredModelResponse] = []
    message: str = ""
