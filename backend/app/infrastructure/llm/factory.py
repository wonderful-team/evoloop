import asyncio
import json
import logging
import weakref
from typing import Any

import httpx

from app.core.file import compute_md5
from app.infrastructure.config import SystemConfigService
from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.infrastructure.llm.thinking_adapter import (
    build_anthropic_thinking_kwargs,
    build_openai_reasoning_extra,
    detect_model_family,
)
from app.infrastructure.schemas import LLMCacheStats, LLMConfig, ThinkingConfig
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)

# Apply reasoning_content patch before any LLM creation
try:
    import app.infrastructure.llm.reasoning_patch  # noqa: F401
except ImportError as e:
    logger.warning(f"[Reasoning] Failed to import patch in factory.py: {e}", exc_info=True)


# --- Thinking-config extra_body builder, shared by platform and direct modes ---
_FAMILY_EXTRA_BUILDERS: dict[str, Any] = {
    "openai_reasoning": build_openai_reasoning_extra,
}


def _build_family_extra(family: str, cfg: ThinkingConfig, caller_extra: dict[str, Any] | None) -> dict[str, Any]:
    """Merge provider-specific thinking params with caller-supplied extra_body.

    family-specific builder takes priority.  For all other families (deepseek,
    openai_compat, …) we fall back to ``cfg.to_extra_body()`` which
    injects ``enable_thinking`` / ``return_reasoning`` style flags.
    """
    builder = _FAMILY_EXTRA_BUILDERS.get(family)
    if builder is not None:
        return {**builder(cfg), **(caller_extra or {})}
    return {**cfg.to_extra_body(), **(caller_extra or {})}


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

        def _safe_openai_del(_self):
            # Do nothing! We manage the httpx client via HTTP_CLIENT_POOL explicitly
            # so we don't need the SDK to asynchronously close it during GC.
            pass

        OpenAIAsyncClient.__del__ = _safe_openai_del
except ImportError:
    pass

try:
    from anthropic._base_client import AsyncAPIClient as AnthropicAsyncClient

    _original_anthropic_del = getattr(AnthropicAsyncClient, "__del__", None)
    if _original_anthropic_del:

        def _safe_anthropic_del(_self):
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


HTTP_CLIENT_POOL = LoopBoundResource(
    factory=lambda: httpx.AsyncClient(
        auth=EvoCloudPlatformAuth(),
        http2=True,
        timeout=httpx.Timeout(300.0, connect=10.0),  # Increased from 60s to 300s for reasoning models
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    ),
    cleanup=_close_client,
    # NOTE: This pool is intentionally excluded from flush_loop_bound_resources()
    # because its httpx clients are shared with cached LLM instances. If the pool
    # is flushed mid-request (e.g. by a BackgroundTask or Celery task running on
    # the same loop), the shared clients are closed permanently, causing
    # "Cannot send a request, as the client has been closed" errors on all
    # subsequent LLM calls until the server is restarted.
    # LLMFactory manages the lifecycle: when the event loop is GC'd, the
    # WeakKeyDictionary entries for both the LLM cache and the httpx pool are
    # cleaned up automatically.
    skip_flush=True,
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
        config_type: str,
        provider: str,
        base_url: str,
        model_name: str,
        temperature: float,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """Generate unique cache key from LLM configuration."""
        key_data = f"{config_type}:{provider}:{base_url}:{model_name}:{temperature}:{max_tokens}:{sorted(kwargs.items())}"
        return compute_md5(key_data)[:16]

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
            model_name = kwargs.pop("model_name", None) or kwargs.pop("model", None) or ""
            if not model_name:
                logger.info("[LLMFactory] No model_name provided; creating platform LLM and letting the cloud gateway pick the default model.")
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
        else:
            # Fallback: check if custom LLM is configured in the database.
            # Only applies in custom mode. In platform mode the request goes to
            # the EvoLoop Gateway which assigns a default model when none is
            # passed; falling back to a stale LLM_BASE_URL here would hijack
            # platform traffic to an old custom endpoint.
            if not config.base_url and SystemConfigService.get_value("LLM_CONFIG_TYPE", "platform") == "custom":
                db_base_url = SystemConfigService.get_value("LLM_BASE_URL")
                db_api_key = SystemConfigService.get_value("LLM_API_KEY")
                if db_base_url:
                    config_type = "direct"
                    base_url = db_base_url
                    db_provider_type = SystemConfigService.get_value("LLM_PROVIDER_TYPE") or "openai"
                    provider = db_provider_type
                    config.base_url = db_base_url
                    config.api_key = config.api_key or db_api_key
                    config.provider_type = db_provider_type
                    if not config.model_name:
                        config.model_name = (
                            SystemConfigService.get_value("CUSTOM_LLM_MODEL")
                            or SystemConfigService.get_value("LLM_MODEL")
                            or ""
                        )
                    if not config.model_name:
                        raise ValueError(
                            "Custom LLM mode requires CUSTOM_LLM_MODEL or LLM_MODEL"
                        )

        # Generate cache key
        cache_key = LLMFactory._generate_cache_key(
            config_type,
            provider,
            base_url,
            config.model_name,
            config.temperature,
            config.max_tokens,
            **config.extra_body,
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

        family = detect_model_family(config.model_name)
        cfg = ThinkingConfig()

        extra_body = _build_family_extra(family, cfg, config.extra_body)

        effective_max_tokens = config.max_tokens

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
            max_tokens=effective_max_tokens,
            http_async_client=HTTP_CLIENT_POOL.get(),
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
        if not config.base_url or not config.api_key:
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

        logger.info(f"[LLMFactory] Direct mode: model={config.model_name}, base_url={config.base_url}")

        return LLMFactory._build_llm_instance(
            api_key=config.api_key or "",
            base_url=config.base_url,
            model_name=config.model_name,
            temperature=config.temperature,
            streaming=config.streaming,
            max_tokens=config.max_tokens,
            extra_body=config.extra_body,
        )

    @staticmethod
    def _build_llm_instance(
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        temperature: float,
        provider_type: str = "",  # deprecated, auto-detected from URL
        streaming: bool = False,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        """Build the actual LLM instance. Provider type is auto-detected from URL."""
        cfg = ThinkingConfig()
        family = detect_model_family(model_name, base_url)

        # --- Anthropic branch: different SDK + URL normalization ---
        if family == "anthropic":
            from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic

            # Anthropic SDK automatically appends /v1/messages to the base_url.
            # Strip trailing /v1 or /v1/ so the SDK constructs the correct path.
            normalized = base_url.rstrip("/")
            if normalized.endswith("/v1"):
                normalized = normalized[:-3]

            thinking_kwargs = build_anthropic_thinking_kwargs(cfg)

            return CompatibleChatAnthropic(
                api_key=api_key,
                base_url=normalized,
                model_name=model_name,
                temperature=temperature,
                streaming=streaming,
                model_kwargs=thinking_kwargs or {},
                http_async_client=HTTP_CLIENT_POOL.get(),
            )

        # --- OpenAI-compatible branch: one path, thinking-extra dispatched by family ---
        db_headers_str = SystemConfigService.get_value("LLM_HEADERS", "{}")
        try:
            final_headers = json.loads(db_headers_str) if db_headers_str else {}
        except json.JSONDecodeError:
            final_headers = {}

        merged_extra = _build_family_extra(family, cfg, extra_body)

        effective_max_tokens = max_tokens

        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model_name,
            temperature=temperature,
            streaming=streaming,
            max_tokens=effective_max_tokens,
            http_async_client=HTTP_CLIENT_POOL.get(),
            extra_body=merged_extra,
            default_headers=final_headers if final_headers else None,
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
        base_url: str, api_key: str, model_name: str, temperature: float = 0.7
    ):
        """
        Create a raw Completion client (Legacy/Text-Generation) for SSM/Flash Brain.
        Useful for endpoints that strictly use /v1/completions.
        """
        import openai

        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm(model_name: str | None = None, temperature: float = 0.3, **kwargs):
    """Get default LLM as an awaitable (Task or coroutine).

    Always returns something ``await``-able so every caller shares one
    contract: ``llm = await get_default_llm(...)``. In an async context the
    coroutine is scheduled as a Task; outside any running loop a bare coroutine
    is returned (the caller supplies the loop via ``await``).

    NOTE: the no-loop fallback creates a coroutine that the caller must drive;
    it never blocks on a fresh ``asyncio.run`` loop, so the event-loop-bound
    ``LLMFactory._instance_cache`` is never silently bypassed.
    """
    config = LLMConfig(model_name=model_name or "", temperature=temperature, **kwargs)

    try:
        return asyncio.create_task(LLMFactory.create_llm(config))
    except RuntimeError:
        logger.warning(
            "[LLMFactory] get_default_llm called outside a running loop; "
            "returning coroutine (caller must await). "
            f"model={config.model_name}, temp={config.temperature}"
        , exc_info=True)
        return LLMFactory.create_llm(config)


async def shutdown_http_pool():
    """Close all cached httpx clients in the shared HTTP client pool.

    Called during application shutdown to properly close connections.
    Iterates all event-loop entries since each loop has its own client.
    """
    logger.info("[LLMFactory] Shutting down HTTP client pool...")
    count = 0
    for _loop, client in list(HTTP_CLIENT_POOL._resources.items()):
        await client.aclose()
        count += 1
    HTTP_CLIENT_POOL._resources.clear()
    logger.info(f"[LLMFactory] HTTP client pool closed ({count} client(s))")
