"""Schemas for infrastructure module."""

import asyncio
from datetime import datetime
from typing import Any, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ToolRequest(DynamicBaseModel):
    """Represents a pending tool execution request."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str
    thread_id: str
    tool: str
    params: dict[str, Any]
    status: str = "pending"  # pending, executing, completed, failed
    result: Any | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    # Async event for waiting
    event: asyncio.Event = Field(default_factory=asyncio.Event, exclude=True)
    future: asyncio.Future | None = Field(default=None, exclude=True)


class TaskEnvelope(DynamicBaseModel):
    """
    Generic envelope for cross-module task dispatching.
    Used when a module wants to hand off work without importing
    the receiver's domain models (Anti-Corruption Layer).
    """

    task_type: str
    payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class ResultEnvelope(DynamicBaseModel):
    """
    Generic envelope for task results returned across module boundaries.
    """

    success: bool = True
    payload: dict[str, Any] | None = None
    error: str | None = None


class LLMCacheStats(DynamicBaseModel):
    """Statistics for the LLM instance cache."""
    cache_hits: int
    cache_misses: int
    hit_rate: str
    cached_instances: int


class ModelProfile(DynamicBaseModel):
    """Profile defining a model's capabilities and tuning parameters."""

    name: str
    max_context_tokens: int
    recommended_output_tokens: int = 4096
    context_window_ratio: float = 0.6  # Use 60% of context for history
    prune_threshold_ratio: float = 0.7  # Start pruning at 70% capacity
    truncate_limit_tokens: int = 5000  # Max tokens per single tool output
    supports_vision: bool = False
    supports_tool_calls: bool = True

    @property
    def effective_history_tokens(self) -> int:
        """Max tokens available for message history."""
        return int(self.max_context_tokens * self.context_window_ratio)

    @property
    def prune_threshold_tokens(self) -> int:
        """Token count at which pruning should trigger."""
        return int(self.effective_history_tokens * self.prune_threshold_ratio)

    @property
    def window_size(self) -> int:
        """
        Recommended message window size.
        Heuristic: average message ~200 tokens.
        """
        avg_msg_tokens = 200
        return max(10, self.effective_history_tokens // avg_msg_tokens)

    @property
    def truncate_limit_chars(self) -> int:
        """Character-based truncate limit (for backward compatibility)."""
        return self.truncate_limit_tokens * 4


class PlatformModel(DynamicBaseModel):
    """平台模型配置"""
    model_id: str
    display_name: str
    provider_name: str
    provider_type: str = "openai"  # openai | anthropic
    model_type: str = "llm"  # llm, embedding, vision
    config_type: str = "evoloop"  # evoloop, custom
    context_window: int = 128000 # Default to 128k as requested
    max_tokens: int = 4096
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_functions: bool = True
    description: str = ""
    icon: str = "default"
    available: bool = True
    quota_required: bool = True

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


class KnowledgeSearchResult(BaseModel):
    """Single search result."""

    doc_id: str
    path: str
    collection: str
    title: str
    content_snippet: str
    highlights: str  # HTML with <mark> tags
    rank: float
    bm25_score: float


class SearchResults(BaseModel):
    """Collection of search results."""

    query: str
    total: int
    results: list[KnowledgeSearchResult]
    facets: dict = Field(default_factory=dict)


class SearchSuggestion(BaseModel):
    """Single search suggestion."""

    text: str
    path: Optional[str] = None
    type: str  # "title", "tag"


class SearchIndexStats(BaseModel):
    """Search index statistics."""

    total_documents: int
    total_terms: int
    collections: list[str]
    recent_searches: list[dict]


class ReindexResult(BaseModel):
    """Result of reindexing all documents."""

    indexed: int
    failed: int
    total: int


class IndexDocumentRequest(BaseModel):
    """Request to index a document."""

    doc_id: str
    path: str
    title: str
    content: str
    collection: str = "default"
    tags: Optional[list[str]] = None
    file_size: Optional[int] = None
    word_count: Optional[int] = None
