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
    default_model_id: str | None = Field(None, description="Selected Default Embedding Model ID")

class SystemStatusResponse(BaseAPIResponse):
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    status: str = "ok"

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

class ResetKnowledgeResponse(BaseAPIResponse):
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

class ProjectDiscoveryConfigUpdateResponse(BaseAPIResponse):
    enabled: bool
    locked: bool | None = None

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
    default_model_id: str | None = Field(None, description="Selected Default Model ID")

class ProjectDiscoveryConfigResponse(BaseAPIResponse):
    enabled: bool
    source: str  # "env" | "config" | "default"

class ProjectDiscoveryConfigRequest(DynamicBaseModel):
    enabled: bool
