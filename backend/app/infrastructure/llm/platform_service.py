"""
LLM Platform Service - 从 EvoLoop Gateway 获取模型配置

注：HTTP 请求逻辑已下沉到 EvoCloudHTTPClient，本模块只保留缓存和格式转换层
"""

import asyncio
import logging
import time

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.evocloud import evocloud_manager
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.schemas import (
    AvailableEmbeddingModel,
    AvailableLLMModel,
    PlatformModel,
)

logger = logging.getLogger(__name__)

# --- Provider guess helpers for static fallback profiles ---
# 只保留 openai / Anthropic / deepseek 三类；其余厂商走默认 OpenAI 兼容解析。
# Order matters: more specific keywords should appear before generic ones.
_PROVIDER_GUESSES: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (("claude", "anthropic"), ("Anthropic", "anthropic")),
    (("deepseek",), ("DeepSeek", "openai")),
    (("gpt", "openai"), ("OpenAI", "openai")),
]


def _guess_provider(model_name: str) -> tuple[str, str]:
    """根据模型名推断 provider_name 与 provider_type（fallback 用）。"""
    n = model_name.lower()
    for keywords, (provider_name, provider_type) in _PROVIDER_GUESSES:
        if any(k in n for k in keywords):
            return provider_name, provider_type
    return "OpenAI", "openai"


class LLMPlatformService:
    """
    从 EvoLoop Gateway 获取 LLM 模型配置 (带本地缓存)
    """

    _instance = None
    _models_cache: dict[str, PlatformModel] = {}
    _last_fetch_time: float = 0
    _cache_ttl: int = 300  # 5分钟缓存
    _fetch_lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # --- Profile & Feature Detection ---
    def get_profile(self, model_name: str) -> PlatformModel:
        """Get the profile (PlatformModel) for a given model name."""
        if not model_name:
            return PlatformModel(
                model_id="unknown",
                display_name="Unknown",
                provider_name="unknown",
                provider_type="openai",
            )

        # --- Phase 1: Try Live Config (The source of truth) ---
        live_model = self.get_model_by_id(model_name)
        if live_model:
            return live_model

        # --- Phase 2: Static Fallback ---
        effective_name = model_name
        if model_name.startswith("custom-"):
            parts = model_name.split("-", 2)
            if len(parts) >= 3:
                effective_name = parts[2]

        configured_vision_model = SystemConfigService.get_value("VISION_MODEL")
        if not configured_vision_model:
            configured_vision_model = SystemConfigService.get_value("CUSTOM_LLM_MODEL") or SystemConfigService.get_value("LLM_MODEL")

        supports_vision = (effective_name == configured_vision_model) if configured_vision_model else False

        provider_name, provider_type = _guess_provider(effective_name)
        return PlatformModel(
            model_id=model_name,
            display_name=model_name,
            provider_name=provider_name,
            provider_type=provider_type,
            context_window=DEFAULT_MAX_CONTEXT_TOKENS,
            supports_vision=supports_vision,
        )

    async def fetch_platform_models(self, force_refresh: bool = False) -> list[PlatformModel]:
        """
        从 EvoLoop Gateway 获取平台模型列表
        使用 EvoCloudHTTPClient 处理 HTTP 请求、认证和路由

        使用锁防止并发请求导致重复 fetch（竞争条件）
        """
        # 快速路径：缓存未过期且非强制刷新，直接返回缓存
        now = time.time()
        if not force_refresh and self._models_cache and (now - self._last_fetch_time) < self._cache_ttl:
            logger.debug("[LLMPlatform] Returning cached models (TTL not expired)")
            return self.get_cached_models()

        # 加锁：防止多个并发请求同时 fetch
        async with self._fetch_lock:
            # 双重检查：拿到锁后缓存可能已更新
            now = time.time()
            if not force_refresh and self._models_cache and (now - self._last_fetch_time) < self._cache_ttl:
                return self.get_cached_models()

            try:
                resp = await evocloud_manager.api.get_llm_models()

                if resp.get("code", -1) != 0:
                    logger.error("[LLMPlatform] API error: %s", resp.get("message", "unknown"))
                    return self._fallback_to_cache()

                # 解析模型列表
                models_data = resp.get("data", {})
                models = models_data.get("models", [])

                new_cache: dict[str, PlatformModel] = {}
                platform_models: list[PlatformModel] = []
                for m in models:
                    if m.get("config_type") != "evoloop":
                        continue

                    model = PlatformModel(
                        model_id=m.get("model_id", ""),
                        display_name=m.get("display_name", ""),
                        provider_name=m.get("provider_name", ""),
                        provider_type=m.get("provider_type", "openai"),
                        model_type=m.get("model_type", "llm"),
                        config_type=m.get("config_type", "evoloop"),
                        context_window=m.get("context_window", 8192),
                        max_tokens=m.get("max_tokens", 4096),
                        supports_streaming=m.get("supports_streaming", True),
                        supports_vision=m.get("supports_vision", False),
                        supports_functions=m.get("supports_functions", True),
                        description=m.get("description", ""),
                        icon=m.get("icon", "default"),
                        available=m.get("available", True),
                        quota_required=m.get("quota_required", True),
                        sort_order=m.get("sort_order", 0),
                    )
                    platform_models.append(model)
                    new_cache[model.model_id] = model

                # 用新缓存完全替换旧缓存，避免已下架模型残留
                self._models_cache.clear()
                self._models_cache.update(new_cache)
                self._last_fetch_time = time.time()

                logger.info("[LLMPlatform] Fetched %d platform models", len(platform_models))
                return platform_models

            except Exception:
                logger.exception("[LLMPlatform] Failed to fetch platform models")
                return self._fallback_to_cache()

    def _fallback_to_cache(self) -> list[PlatformModel]:
        """Fetch 失败时返回缓存（如有），避免 UI 列表直接变空。"""
        if self._models_cache:
            logger.warning("[LLMPlatform] Returning stale cached models due to fetch failure")
            return self.get_cached_models()
        return []

    def get_cached_models(self) -> list[PlatformModel]:
        """获取缓存的模型列表"""
        return list(self._models_cache.values())

    def get_model_by_id(self, model_id: str) -> PlatformModel | None:
        """根据 ID 获取模型配置"""
        return self._models_cache.get(model_id)

    def clear_cache(self):
        """清除缓存"""
        self._models_cache.clear()
        self._last_fetch_time = 0


# 全局实例
llm_platform_service = LLMPlatformService()


async def get_available_llm_models(config_type: str | None = None) -> list[AvailableLLMModel]:
    """
    获取可用的 LLM 模型列表 (platform + custom 组合)

    - platform: 从 EvoLoop Gateway 获取的模型（需要配额）
    - custom: 用户自己配置的模型（使用自己的 API Key）
    """
    # 如果未指定 config_type，从系统配置获取
    if config_type is None:
        config_type = SystemConfigService.get_value("LLM_CONFIG_TYPE", "platform")

    result: list[AvailableLLMModel] = []

    # 1. 获取 Platform 模型（从 EvoLoop Gateway）
    if config_type != "custom":
        platform_models = await llm_platform_service.fetch_platform_models()
        for m in platform_models:
            if m.model_type != "llm":  # 只保留 LLM 模型
                continue

            result.append(
                AvailableLLMModel(
                    id=m.model_id,
                    name=m.display_name,
                    type="platform",
                    provider=m.provider_name,
                    provider_type=m.provider_type,
                    model=m.model_id,
                    vision_model=m.model_id if m.supports_vision else None,
                    description=m.description or f"使用 EvoLoop 平台提供的 {m.display_name}",
                    icon=m.icon,
                    available=m.available,
                    quota_required=True,
                    supports_streaming=m.supports_streaming,
                    supports_vision=m.supports_vision,
                    supports_functions=m.supports_functions,
                    context_window=m.context_window,
                )
            )

    # 2. 获取 Custom 模型（用户自己配置的）
    if config_type != "platform":
        custom_provider = SystemConfigService.get_value("LLM_PROVIDER")
        custom_provider_type = SystemConfigService.get_value("LLM_PROVIDER_TYPE", "openai")
        # 优先从 CUSTOM_LLM_MODEL 获取，如果没有则回退回 LLM_MODEL (兼容旧版本)
        custom_model = SystemConfigService.get_value("CUSTOM_LLM_MODEL") or SystemConfigService.get_value("LLM_MODEL")
        custom_api_key = SystemConfigService.get_value("LLM_API_KEY")

        if custom_provider and custom_model and custom_api_key and not custom_model.startswith("custom-"):
            # 构建 custom 模型 ID
            custom_id = f"custom-{custom_provider}-{custom_model}"

            # 从配置获取 vision model
            vision_model = SystemConfigService.get_value("VISION_MODEL", custom_model)

            # Get profile for custom model to determine context window
            profile = llm_platform_service.get_profile(custom_model)

            result.append(
                AvailableLLMModel(
                    id=custom_id,
                    name=f"{custom_model} (Custom)",
                    type="custom",
                    provider=custom_provider,
                    provider_type=custom_provider_type,
                    model=custom_model,
                    vision_model=vision_model if vision_model != custom_model else None,
                    description=f"使用自己的 {custom_provider.upper()} API Key",
                    icon=custom_provider,
                    available=True,
                    quota_required=False,
                    supports_streaming=True,
                    supports_vision=profile.supports_vision,
                    supports_functions=profile.supports_functions,
                    context_window=profile.context_window,
                )
            )

    return result


async def get_available_embedding_models() -> list[AvailableEmbeddingModel]:
    """
    获取可用的 Embedding 模型列表 (platform + custom 组合)

    - platform: 从 EvoLoop Gateway 获取的模型（需要配额）
    - custom: 用户自己配置的模型（使用自己的 API Key）
    """
    result: list[AvailableEmbeddingModel] = []

    # 1. 获取 Platform Embedding 模型（从 EvoLoop Gateway）
    platform_models = await llm_platform_service.fetch_platform_models()
    for m in platform_models:
        if m.model_type != "embedding":
            continue

        result.append(
            AvailableEmbeddingModel(
                id=f"embedding-{m.model_id}",
                name=m.display_name,
                type="platform",
                provider=m.provider_name,
                model=m.model_id,
                dimensions=1536,  # 默认值，实际应从配置获取
                description=m.description
                or f"使用 EvoLoop 平台提供的 {m.display_name}",
                icon=m.icon,
                available=m.available,
                quota_required=True,
            )
        )

    # 2. 获取 Custom Embedding 模型（用户自己配置的）
    embedding_provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
    # 优先从 CUSTOM_EMBEDDING_MODEL 获取，如果没有则回退回 EMBEDDING_MODEL (兼容旧版本)
    embedding_model = SystemConfigService.get_value("CUSTOM_EMBEDDING_MODEL") or SystemConfigService.get_value("EMBEDDING_MODEL")
    embedding_api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")

    if embedding_provider and embedding_model and embedding_api_key and not embedding_model.startswith("embedding-"):
        # 根据 provider 推断 dimensions
        dimensions_map = {
            "openai": 1536,
            "ollama": 768,
            "dashscope": 1536,
            "huggingface": 768,
        }
        dimensions = dimensions_map.get(embedding_provider, 1536)

        custom_id = f"custom-embedding-{embedding_provider}-{embedding_model}"

        result.append(
            AvailableEmbeddingModel(
                id=custom_id,
                name=f"{embedding_model} (Custom)",
                type="custom",
                provider=embedding_provider,
                model=embedding_model,
                dimensions=dimensions,
                description=f"使用自己的 {embedding_provider.upper()} Embedding API Key",
                icon=embedding_provider,
                available=True,
                quota_required=False,
            )
        )

    return result
