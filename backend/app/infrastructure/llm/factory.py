import asyncio
import hashlib
import httpx
import logging
from typing import Dict, Tuple

from langchain_anthropic import ChatAnthropic

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
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
    def _generate_cache_key(provider: str, base_url: str, model_name: str, 
                           temperature: float, **kwargs) -> str:
        """Generate unique cache key from LLM configuration."""
        key_data = f"{provider}:{base_url}:{model_name}:{temperature}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    @staticmethod
    async def create_llm(model_name: str | None = None, temperature: float = 0.3, **kwargs):
        """
        Create a standard LLM instance with caching.
        
        Prioritizes SystemConfig (Dynamic) > Settings (Env Checks).
        Returns cached instance if configuration matches.
        """
        from app.infrastructure.config.service import SystemConfigService

        # 1. Fetch Config
        provider = SystemConfigService.get_value("LLM_PROVIDER")
        base_url = SystemConfigService.get_value("LLM_BASE_URL")
        model_name = model_name or SystemConfigService.get_value("LLM_MODEL")
        api_key = SystemConfigService.get_value("LLM_API_KEY")

        # Generate cache key
        cache_key = LLMFactory._generate_cache_key(
            provider, base_url, model_name, temperature, **kwargs
        )
        
        # Check cache with lock for thread safety
        if cache_key in LLMFactory._instance_cache:
            LLMFactory._cache_hits += 1
            logger.debug(f"[LLMFactory] Cache hit for {cache_key} (hits: {LLMFactory._cache_hits})")
            return LLMFactory._instance_cache[cache_key]
        
        async with LLMFactory._cache_lock:
            # Double-check after acquiring lock
            if cache_key in LLMFactory._instance_cache:
                LLMFactory._cache_hits += 1
                return LLMFactory._instance_cache[cache_key]
            
            LLMFactory._cache_misses += 1
            logger.info(f"[LLMFactory] Creating new LLM instance: {provider}/{model_name} "
                       f"(hits: {LLMFactory._cache_hits}, misses: {LLMFactory._cache_misses})")

            # Create new instance
            instance = LLMFactory._create_llm_internal(
                provider=provider,
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
                temperature=temperature,
                **kwargs
            )
            
            # Cache the instance
            LLMFactory._instance_cache[cache_key] = instance
            
            # Limit cache size to prevent memory leak
            if len(LLMFactory._instance_cache) > 10:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(LLMFactory._instance_cache))
                del LLMFactory._instance_cache[oldest_key]
                logger.debug(f"[LLMFactory] Evicted oldest cache entry: {oldest_key}")
            
            return instance

    @staticmethod
    def _create_llm_internal(provider: str, base_url: str, model_name: str, 
                            api_key: str, temperature: float, **kwargs):
        """Internal method to create LLM instance (without caching)."""
        
        # Anthropic / Claude Protocol Support (Zhipu, Kimi, etc.)
        if provider in ["anthropic", "kimi"] or "api/anthropic" in (base_url or ""):
            from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic

            # Check for Zhipu GLM-4 (requires response patching)
            if "bigmodel.cn" in (base_url or ""):
                return CompatibleChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    streaming=False,
                    fix_tool_args_list=True,
                    repair_history=True,
                    timeout=300.0,
                    http_async_client=_HTTP_CLIENT_POOL.get(),
                )

            # Check for Kimi / Moonshot
            if any(domain in (base_url or "") for domain in ["moonshot.cn", "kimi.ai", "kimi.com"]):
                return CompatibleChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    streaming=False,
                    fix_tool_args_list=False,
                    repair_history=True,
                    timeout=300.0,
                    http_async_client=_HTTP_CLIENT_POOL.get(),
                )

            return CompatibleChatAnthropic(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                streaming=False,
                timeout=300.0,
                http_async_client=_HTTP_CLIENT_POOL.get(),
            )

        # Default: OpenAI Compatible (Adaptive)
        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            streaming=True,
            http_async_client=_HTTP_CLIENT_POOL.get(),
        )

    @staticmethod
    def get_cache_stats() -> dict:
        """Get LLM instance cache statistics."""
        total = LLMFactory._cache_hits + LLMFactory._cache_misses
        hit_rate = LLMFactory._cache_hits / total if total > 0 else 0
        return {
            "cache_hits": LLMFactory._cache_hits,
            "cache_misses": LLMFactory._cache_misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cached_instances": len(LLMFactory._instance_cache),
        }

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
            max_tokens=512
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm(temperature: float = 0.3):
    """Get default LLM (async wrapper for backward compatibility)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If in async context, use create_task
            return asyncio.create_task(LLMFactory.create_llm(temperature=temperature))
        else:
            return loop.run_until_complete(LLMFactory.create_llm(temperature=temperature))
    except RuntimeError:
        # No event loop, create new one
        return asyncio.run(LLMFactory.create_llm(temperature=temperature))
