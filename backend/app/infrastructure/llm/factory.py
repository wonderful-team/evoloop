import asyncio
import hashlib
import logging
from typing import Dict, Any

import httpx

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.infrastructure.schemas import LLMCacheStats, ThinkingConfig, LLMConfig
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
    def _generate_cache_key(
        config_type: str, provider: str, base_url: str, model_name: str, temperature: float, **kwargs
    ) -> str:
        """Generate unique cache key from LLM configuration."""
        key_data = f"{config_type}:{provider}:{base_url}:{model_name}:{temperature}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    @staticmethod
    async def create_llm(config: LLMConfig | str | None = None, **kwargs) -> Any:
        """
        Create a standard LLM instance using structured configuration.
        """
        # 兼容性处理：如果第一个参数是 None，尝试从 kwargs 提取 model_name
        if config is None:
            model_name = kwargs.pop("model_name", None) or kwargs.pop("model", None)
            if not model_name:
                raise ValueError("[LLMFactory] model_name or LLMConfig must be specified.")
            config = LLMConfig(model_name=model_name, **kwargs)
        
        # 将字符串类型的 model_name 转换为 LLMConfig
        if isinstance(config, str):
            config = LLMConfig(model_name=config, **kwargs)
            
        logger.debug(f"[LLMFactory] Creating LLM: {config.model_name}")

        # Detect Mode and Instantiate
        if config.model_name.startswith("custom-"):
            return await LLMFactory._create_custom_llm(config)

        if config.base_url or config.api_key:
            return await LLMFactory._create_direct_llm(config)

        return await LLMFactory._create_platform_llm(config)

    @staticmethod
    async def _create_platform_llm(config: LLMConfig):
        """
        Platform Mode: Always use OpenAI format to Gateway.
        """
        from app.core.evocloud import evocloud_manager

        token = evocloud_manager.get_token()
        if not token:
            raise ValueError("Not authenticated with EvoLoop platform. Please login first.")

        gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
        if not gateway_url:
            raise ValueError("EvoLoop Gateway URL not configured")

        # Apply reasoning_content patch
        import app.core.engine.reasoning  # noqa: F401

        # Merge standard thinking config into extra_body
        extra_body = {
            **ThinkingConfig().to_extra_body(),
            **config.extra_body
        }

        return AdaptiveChatOpenAI(
            api_key=token,
            base_url=f"{gateway_url}/gateway/v1",
            model=config.model_name,
            temperature=config.temperature,
            streaming=config.streaming,
            max_tokens=config.max_tokens,
            http_async_client=_HTTP_CLIENT_POOL.get(),
            model_kwargs={"extra_body": extra_body},
        )

    @staticmethod
    async def _create_custom_llm(config: LLMConfig):
        """
        Custom Mode: Direct connection to provider.
        """
        # Parse custom-{provider}-{model}
        parts = config.model_name.split("-", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid custom model ID: {config.model_name}")
        
        custom_provider = parts[1]
        actual_model = parts[2]
        
        # Use explicit overrides if provided, otherwise fall back to global config
        if not config.base_url or not config.api_key or not config.provider_type:
            from app.infrastructure.config.service import SystemConfigService
            config.provider_type = config.provider_type or SystemConfigService.get_value("LLM_PROVIDER_TYPE")
            config.base_url = config.base_url or SystemConfigService.get_value("LLM_BASE_URL")
            config.api_key = config.api_key or SystemConfigService.get_value("LLM_API_KEY")
        
        if not config.base_url or not config.api_key:
            raise ValueError(f"Custom model '{actual_model}' requires LLM_BASE_URL and LLM_API_KEY")
        
        logger.info(f"[LLMFactory] Custom mode: provider={custom_provider}, model={actual_model}")
        
        return LLMFactory._build_llm_instance(
            api_key=config.api_key,
            base_url=config.base_url,
            model_name=actual_model,
            temperature=config.temperature,
            provider_type=config.provider_type,
            streaming=config.streaming,
            max_tokens=config.max_tokens,
            extra_body=config.extra_body,
        )

    @staticmethod
    async def _create_direct_llm(config: LLMConfig):
        """
        Direct connection mode for independent endpoints.
        """
        if not config.base_url:
            raise ValueError(f"Direct model '{config.model_name}' requires base_url")
        
        # Use explicit provider_type or detect from URL
        if not config.provider_type:
            config.provider_type = LLMFactory._detect_provider_from_url(config.base_url)
        
        logger.info(f"[LLMFactory] Direct mode: model={config.model_name}, base_url={config.base_url}")
        
        return LLMFactory._build_llm_instance(
            api_key=config.api_key or "",
            base_url=config.base_url,
            model_name=config.model_name,
            temperature=config.temperature,
            provider_type=config.provider_type,
            streaming=config.streaming,
            max_tokens=config.max_tokens,
            extra_body=config.extra_body,
        )

    @staticmethod
    def _detect_provider_from_url(base_url: str) -> str:
        """Detect provider type from URL patterns."""
        url = base_url.lower()
        if "anthropic" in url:
            return "anthropic"
        return "openai"

    @staticmethod
    def _build_llm_instance(
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        temperature: float,
        provider_type: str,
        streaming: bool = False,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        """Build the actual LLM instance based on provider_type."""
        # 导入 reasoning 确保对 ChatOpenAI 的 patch 已应用
        import app.core.engine.reasoning  # noqa: F401

        # 统一的 thinking 配置
        # 使用 extra_body 避免 OpenAI SDK 校验失败
        thinking_extra = ThinkingConfig().to_extra_body()
        merged_extra = {**thinking_extra, **(extra_body or {})}

        if provider_type == "anthropic":
            from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic
            return CompatibleChatAnthropic(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model_name=model_name,
                temperature=temperature,
                streaming=streaming,
                http_async_client=_HTTP_CLIENT_POOL.get(),
            )
        else:
            # openai, deepseek, moonshot, ollama, vllm, etc.
            return AdaptiveChatOpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model=model_name,
                temperature=temperature,
                streaming=streaming,
                max_tokens=max_tokens,
                http_async_client=_HTTP_CLIENT_POOL.get(),
                model_kwargs={"extra_body": merged_extra},
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
def get_default_llm(model_name: str | None = None, temperature: float = 0.3, **kwargs):
    """Get default LLM (async wrapper for backward compatibility)."""
    import asyncio
    config = LLMConfig(model_name=model_name or "gpt-3.5-turbo", temperature=temperature, **kwargs)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.create_task(LLMFactory.create_llm(config))
        else:
            return loop.run_until_complete(LLMFactory.create_llm(config))
    except RuntimeError:
        return asyncio.run(LLMFactory.create_llm(config))
