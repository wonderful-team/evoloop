"""Schemas for infrastructure module."""

from typing import Any, Literal

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class LLMCacheStats(DynamicBaseModel):
    """Statistics for the LLM instance cache."""

    cache_hits: int
    cache_misses: int
    hit_rate: str
    cached_instances: int


class PlatformModel(DynamicBaseModel):
    """平台模型配置"""

    model_id: str
    display_name: str
    provider_name: str
    provider_type: str = "openai"  # openai | anthropic
    model_type: str = "llm"  # llm, embedding, vision, image, video
    config_type: str = "evoloop"  # evoloop, custom
    context_window: int = 128000  # Default to 128k as requested
    max_tokens: int = 4096
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_functions: bool = True
    supports_image_generation: bool = False
    supports_video_generation: bool = False
    description: str = ""
    icon: str = "default"
    available: bool = True
    quota_required: bool = True
    sort_order: int = 0

    # --- Engine Tuning Parameters (formerly in ModelProfile) ---
    context_window_ratio: float = 0.6  # Use 60% of context for history
    prune_threshold_ratio: float = 0.7  # Start pruning at 70% capacity
    truncate_limit_tokens: int = 5000  # Max tokens per single tool output

    @property
    def max_context_tokens(self) -> int:
        """Alias for context_window (compatibility with ModelProfile interface)."""
        from app.constants import DEFAULT_MAX_CONTEXT_TOKENS

        return self.context_window or DEFAULT_MAX_CONTEXT_TOKENS

    @property
    def effective_history_tokens(self) -> int:
        """Max tokens available for message history."""
        return int(self.context_window * self.context_window_ratio)

    @property
    def prune_threshold_tokens(self) -> int:
        """Token count at which pruning should trigger."""
        return int(self.effective_history_tokens * self.prune_threshold_ratio)

    @property
    def truncate_limit_chars(self) -> int:
        """Character-based truncate limit (for backward compatibility)."""
        return self.truncate_limit_tokens * 4


class AvailableLLMModel(DynamicBaseModel):
    """API/内部调用中可用的 LLM 模型条目（platform + custom）。"""

    id: str
    name: str
    type: str  # platform | custom
    provider: str
    provider_type: str
    model: str
    vision_model: str | None = None
    description: str = ""
    icon: str = "default"
    available: bool = True
    quota_required: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_functions: bool = True
    context_window: int = 128000


class AvailableEmbeddingModel(DynamicBaseModel):
    """API/内部调用中可用的 Embedding 模型条目（platform + custom）。"""

    id: str
    name: str
    type: str  # platform | custom
    provider: str
    model: str
    dimensions: int = 1536
    description: str = ""
    icon: str = "default"
    available: bool = True
    quota_required: bool = True


class LLMConfig(DynamicBaseModel):
    """LLM 实例化配置"""

    model_name: str
    temperature: float = 0.3
    base_url: str | None = None
    api_key: str | None = None
    provider_type: str | None = None
    streaming: bool = False
    max_tokens: int | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ThinkingConfig(DynamicBaseModel):
    """LLM 推理意图配置（Provider 无关的抽象层）"""

    enable: bool = True
    return_reasoning: bool = True
    # 语义化深度意图，None = 跟随模型默认，不注入任何约束
    reasoning_effort: Literal["low", "medium", "high", "max"] | None = "high"

    def to_extra_body(self) -> dict[str, Any]:
        """仅生成 OpenAI 兼容层的通用字段（enable/return 开关）
        budget/effort 等 Provider 专属参数由 thinking_adapter 按需注入
        """
        return {
            "enable_thinking": self.enable,
            "return_reasoning": self.return_reasoning,
        }
