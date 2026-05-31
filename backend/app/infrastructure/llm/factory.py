import asyncio
import hashlib
import logging
import weakref
from typing import Any

import httpx

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.infrastructure.schemas import LLMCacheStats, LLMConfig, ThinkingConfig
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)

# Apply reasoning_content patch before any LLM creation
try:
    import app.core.engine.message.reasoning  # noqa: F401
except Exception as e:
    logger.warning(f"[Reasoning] Failed to import patch in factory.py: {e}")


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


class EvoCloudPlatformAuth(httpx.Auth):
    """
    Custom httpx Auth for EvoLoop Platform LLM requests.
    Automatically detects requests to the EvoLoop Gateway and:
    - Injects the latest access token from identity_service.
    - Handles 401 Unauthorized by refreshing the token and retrying.
    """

    async def async_auth_flow(self, request):
        from app.core.evocloud import evocloud_manager

        # 1. Identify if this is a platform request
        gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
        is_platform = gateway_url and str(request.url).startswith(gateway_url)

        if not is_platform:
            # Not a platform request (e.g. direct OpenAI/Anthropic), pass through
            yield request
            return

        # 2. Always inject the LATEST token from identity_service
        # This ensures we are not stuck with an old token even if the LLM instance is cached.
        token = await evocloud_manager.get_token()
        if token:
            request.headers["Authorization"] = f"Bearer {token}"

        # 3. Send request
        response = yield request

        # 4. Handle 401 automatically
        if response.status_code == 401:
            logger.warning(f"[LLMAuth] Platform token expired (401) for {request.url.path}, attempting background refresh...")
            # Trigger refresh (using our lock mechanism in http_client)
            new_token = await evocloud_manager.api.refresh_access_token(failed_token=token)
            if new_token:
                logger.info("[LLMAuth] Token refreshed successfully, retrying request...")
                request.headers["Authorization"] = f"Bearer {new_token}"
                yield request


_HTTP_CLIENT_POOL = LoopBoundResource(
    factory=lambda: httpx.AsyncClient(
        auth=EvoCloudPlatformAuth(),
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

    # Cache: per-event-loop dict of (cache_key) -> LLM instance
    # WeakKeyDictionary ensures entries are auto-removed when the loop is GC'd,
    # preventing stale references across asyncio.run() boundaries in worker tasks.
    _instance_cache: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, Any]] = weakref.WeakKeyDictionary()
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
        Includes instance caching to avoid redundant initialization.

        Performance notes:
        - Fast-path cache check without lock for the common case (cache hit).
        - Instance creation (which may involve I/O like token retrieval) happens
          OUTSIDE the lock so it never blocks creation of other cache keys.
        - Double-checked locking prevents redundant creation for the same key
          when two coroutines race past the fast-path check.
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

        # Determine mode for cache key
        config_type = "standard"
        provider = "platform"
        base_url = ""

        if config.model_name.startswith("custom-"):
            config_type = "custom"
            provider = config.model_name.split("-")[1]
        elif config.base_url or config.api_key:
            config_type = "direct"
            base_url = config.base_url or ""

        # Generate cache key
        cache_key = LLMFactory._generate_cache_key(
            config_type, provider, base_url, config.model_name, config.temperature, **config.extra_body
        )

        # ---------- Fast path: check cache without lock ----------
        loop = asyncio.get_running_loop()
        loop_cache = LLMFactory._instance_cache.get(loop)
        if loop_cache and cache_key in loop_cache:
            LLMFactory._cache_hits += 1
            return loop_cache[cache_key]

        # ---------- Instance creation (outside lock) ----------
        if config_type == "custom":
            instance = await LLMFactory._create_custom_llm(config)
        elif config_type == "direct":
            instance = await LLMFactory._create_direct_llm(config)
        else:
            instance = await LLMFactory._create_platform_llm(config)

        # ---------- Store in cache with double-checked locking ----------
        async with LLMFactory._cache_lock:
            loop = asyncio.get_running_loop()
            loop_cache = LLMFactory._instance_cache.get(loop)
            if loop_cache is None:
                loop_cache = {}
                LLMFactory._instance_cache[loop] = loop_cache

            if cache_key in loop_cache:
                # Another coroutine stored it while we were creating — use the cached one
                LLMFactory._cache_hits += 1
                return loop_cache[cache_key]

            LLMFactory._cache_misses += 1
            logger.debug(
                f"[LLMFactory] Creating new LLM instance: {config.model_name} "
                f"(type={config_type}, temp={config.temperature}, key={cache_key})"
            )

            loop_cache[cache_key] = instance
            return instance

    @staticmethod
    async def _create_platform_llm(config: LLMConfig):
        """
        Platform Mode: Use dynamic auth via PLATFORM_TOKEN placeholder.
        """
        from app.core.evocloud import evocloud_manager

        gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
        if not gateway_url:
            raise ValueError("EvoLoop Gateway URL not configured")

        # Merge standard thinking config into extra_body
        extra_body = {
            **ThinkingConfig().to_extra_body(),
            **config.extra_body
        }

        # Use the current token for initialization.
        # Note: EvoCloudPlatformAuth will automatically replace it with
        # the latest token at request-time if it changes in the background.
        token = await evocloud_manager.get_token() or ""

        return AdaptiveChatOpenAI(
            api_key=token,
            base_url=f"{gateway_url}/gateway/v1",
            model=config.model_name,
            temperature=config.temperature,
            streaming=config.streaming,
            max_tokens=config.max_tokens,
            http_async_client=_HTTP_CLIENT_POOL.get(),
            extra_body=extra_body,
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
                extra_body=merged_extra,
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
            cached_instances=sum(len(c) for c in LLMFactory._instance_cache.values()),
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
    """Get default LLM (async wrapper for backward compatibility).

    NOTE: The ``asyncio.run()`` fallback (line 408) creates a *new* event loop,
    which means the LLM instance cannot be cached by
    ``LLMFactory._instance_cache`` (a ``WeakKeyDictionary`` keyed by event loop).
    Every call to this fallback path will create a fresh LLM instance and then
    discard the loop, guaranteeing a cache miss for subsequent calls.
    If you see repeated \"Creating new LLM instance\" log entries for the same
    configuration, check whether this fallback is being triggered and convert
    the caller to use ``await get_default_llm(...)`` or
    ``await LLMFactory.create_llm(...)`` directly instead.
    """
    import asyncio
    config = LLMConfig(model_name=model_name or "gpt-3.5-turbo", temperature=temperature, **kwargs)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.create_task(LLMFactory.create_llm(config))
        else:
            return loop.run_until_complete(LLMFactory.create_llm(config))
    except RuntimeError:
        logger.warning(
            f"[LLMFactory] get_default_llm falling back to asyncio.run() — "
            f"new event loop will bypass the instance cache. "
            f"model={config.model_name}, temp={config.temperature}"
        )
        return asyncio.run(LLMFactory.create_llm(config))
