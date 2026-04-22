import asyncio
import hashlib
import logging
from typing import Dict

import httpx

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


# Global Shared HTTP Client for Connection Pooling (HTTP/2 enabled), per Event Loop
async def _close_client(client: httpx.AsyncClient):
    await client.aclose()


# --- Monkeypatch to prevent SDKs from creating background aclose tasks during GC ---
# This prevents "Task exception was never retrieved" and "Event loop is closed" errors
# when Celery tasks shut down their event loops and GC destroys the LLM clients.
try:
    from openai._base_client import AsyncAPIClient as OpenAIAsyncClient
    _original_openai_del = getattr(OpenAIAsyncClient, "__del__", None)
    if _original_openai_del:
        def _safe_openai_del(self):
            # Do nothing! We manage the httpx client via _HTTP_CLIENT_POOL explicitly
            # so we don't need the SDK to asynchronously close it during GC.
            pass
        OpenAIAsyncClient.__del__ = _safe_openai_del
except ImportError:
    pass

try:
    from anthropic._base_client import AsyncAPIClient as AnthropicAsyncClient
    _original_anthropic_del = getattr(AnthropicAsyncClient, "__del__", None)
    if _original_anthropic_del:
        def _safe_anthropic_del(self):
            pass
        AnthropicAsyncClient.__del__ = _safe_anthropic_del
except ImportError:
    pass

_HTTP_CLIENT_POOL = LoopBoundResource(
    factory=lambda: httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(300.0, connect=10.0), # Increased from 60s to 300s for reasoning models
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    ),
    cleanup=_close_client
)


class LLMCacheStats(DynamicBaseModel):
    """Statistics for the LLM instance cache."""
    cache_hits: int
    cache_misses: int
    hit_rate: str
    cached_instances: int


class LLMFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    
    Optimization:
    - Instance caching: Reuses LLM instances with same config to avoid
      redundant initialization overhead (~8ms per call).
    - Thread-safe with asyncio.Lock for concurrent access.
    """
    
    # Cache: (cache_key) -> LLM instance
    _instance_cache: Dict[str, any] = {}
    _cache_lock = asyncio.Lock()
    _cache_hits = 0
    _cache_misses = 0

    @staticmethod
    def _generate_cache_key(
        config_type: str, provider: str, base_url: str, model_name: str, temperature: float, **kwargs
    ) -> str:
        """Generate unique cache key from LLM configuration."""
        key_data = f"{config_type}:{provider}:{base_url}:{model_name}:{temperature}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    @staticmethod
    async def create_llm(model_name: str | None = None, temperature: float = 0.3, **kwargs):
        """
        Create a standard LLM instance.
        
        Architecture:
        - Platform Mode: Backend → Gateway (OpenAI format) → Gateway handles protocol translation
        - Custom Mode: Backend → Direct connection (Backend handles protocol selection)
        """
        logger.debug(f"[LLMFactory] Creating LLM with model_name={model_name}")
        
        # 2. Detect Mode and Instantiate
        if model_name.startswith("custom-"):
            return await LLMFactory._create_custom_llm(model_name, temperature, **kwargs)

        return await LLMFactory._create_platform_llm(model_name, temperature, **kwargs)

    @staticmethod
    async def _create_platform_llm(model_name: str | None, temperature: float, **kwargs):
        """
        Platform Mode: Always use OpenAI format to Gateway.
        Gateway handles protocol translation based on provider_type.
        """
        from app.core.evocloud import evocloud_manager

        token = evocloud_manager.get_token()
        if not token:
            raise ValueError("Not authenticated with EvoLoop platform. Please login first.")

        gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
        if not gateway_url:
            raise ValueError("EvoLoop Gateway URL not configured")

        # model_name is guaranteed by the caller (create_llm)
        # Backend always sends OpenAI format to Gateway
        # Gateway handles protocol translation (OpenAI ↔ Anthropic)
        return AdaptiveChatOpenAI(
            api_key=token,
            base_url=f"{gateway_url}/gateway/v1",
            model=model_name,
            temperature=temperature,
            streaming=kwargs.get("streaming", False),
            http_async_client=_HTTP_CLIENT_POOL.get(),
        )

    @staticmethod
    async def _create_custom_llm(model_name: str, temperature: float, **kwargs):
        """
        Custom Mode: Direct connection to provider.
        Backend selects adapter based on provider_type.
        """
        from app.infrastructure.config.service import SystemConfigService
        
        # Parse custom-{provider}-{model}
        parts = model_name.split("-", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid custom model ID: {model_name}")
        
        custom_provider = parts[1]
        actual_model = parts[2]
        
        # Get configuration
        provider_type = SystemConfigService.get_value("LLM_PROVIDER_TYPE")
        base_url = SystemConfigService.get_value("LLM_BASE_URL")
        api_key = SystemConfigService.get_value("LLM_API_KEY")
        
        if not base_url or not api_key:
            raise ValueError(f"Custom model '{actual_model}' requires LLM_BASE_URL and LLM_API_KEY")
        
        logger.info(f"[LLMFactory] Custom mode: provider={custom_provider}, type={provider_type}, model={actual_model}")
        
        # streaming 参数可从 kwargs 传入，默认为 False
        streaming = kwargs.get("streaming", False)
        
        # Select adapter based on provider_type
        if provider_type == "anthropic":
            from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic
            return CompatibleChatAnthropic(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model_name=actual_model,
                temperature=temperature,
                streaming=streaming,
                http_async_client=_HTTP_CLIENT_POOL.get(),
            )
        else:
            # openai, deepseek, moonshot, etc.
            return AdaptiveChatOpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model=actual_model,
                temperature=temperature,
                streaming=streaming,
                http_async_client=_HTTP_CLIENT_POOL.get(),
            )

    @staticmethod
    def get_cache_stats() -> LLMCacheStats:
        """Get LLM instance cache statistics."""
        total = LLMFactory._cache_hits + LLMFactory._cache_misses
        hit_rate = LLMFactory._cache_hits / total if total > 0 else 0
        return LLMCacheStats(
            cache_hits=LLMFactory._cache_hits,
            cache_misses=LLMFactory._cache_misses,
            hit_rate=f"{hit_rate:.1%}",
            cached_instances=len(LLMFactory._instance_cache),
        )

    @staticmethod
    def clear_cache():
        """Clear the LLM instance cache."""
        LLMFactory._instance_cache.clear()
        LLMFactory._cache_hits = 0
        LLMFactory._cache_misses = 0
        logger.info("[LLMFactory] Cache cleared")

    @staticmethod
    def create_completion_client(
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7
    ):
        """
        Create a raw Completion client (Legacy/Text-Generation) for SSM/Flash Brain.
        Useful for endpoints that strictly use /v1/completions.
        """
        from langchain_openai import OpenAI
        return OpenAI(
            openai_api_key=api_key,
            openai_api_base=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=8192
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm(temperature: float = 0.3, **kwargs):
    """Get default LLM (async wrapper for backward compatibility).
    
    Args:
        temperature: Sampling temperature
        **kwargs: Additional arguments passed to LLMFactory.create_llm (e.g., max_tokens)
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If in async context, use create_task
            return asyncio.create_task(LLMFactory.create_llm(temperature=temperature, **kwargs))
        else:
            return loop.run_until_complete(LLMFactory.create_llm(temperature=temperature, **kwargs))
    except RuntimeError:
        # No event loop, create new one
        return asyncio.run(LLMFactory.create_llm(temperature=temperature, **kwargs))
