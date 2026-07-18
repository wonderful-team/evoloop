import logging
import threading

from app.core.config import settings
from app.infrastructure.config import SystemConfigService
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.local import LocalEmbedder
from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

logger = logging.getLogger(__name__)


def _svc(key: str, default: str | None = None) -> str | None:
    """Read a system config value with safe fallback."""
    try:
        return SystemConfigService.get_value(key, default)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
        return default


class EmbedderFactory:
    """Creates and caches the configured Embedder.

    Resolution follows a priority chain (EMBEDDING_TIERS):
      Tier 1 "gguf"   : llama.cpp embedder via LocalEmbedder
      Tier 2 "local"  : LM Studio / Ollama via GenericOpenAIEmbedder
      Tier 3 "remote" : configured provider (openai, ollama, lm-studio, …)

    Falls back to the next tier when the current one is unavailable.
    Results are cached so repeated calls reuse the same in-memory model.

    Thread-safety:
        A threading.Lock protects the shared cache. The expensive embedder
        creation happens outside the lock.
    """

    _instances: dict[str, BaseEmbedder] = {}
    _default_key: str = "__default__"
    _lock = threading.Lock()

    @classmethod
    def get_embedder(cls, model_name: str | None = None) -> BaseEmbedder:
        cache_key = model_name or cls._default_key

        with cls._lock:
            cached = cls._instances.get(cache_key)
        if cached is not None:
            return cached

        embedder = cls._create_embedder(model_name, cache_key)

        with cls._lock:
            if cache_key not in cls._instances:
                cls._instances[cache_key] = embedder
            return cls._instances[cache_key]

    @classmethod
    def _create_embedder(cls, model_name: str | None, cache_key: str) -> BaseEmbedder:
        if model_name and (model_name.startswith("custom-embedding-") or model_name.startswith("custom-")):
            return cls._create_custom_embedding(model_name)

        raw_tiers = _svc("EMBEDDING_TIERS")
        if not raw_tiers:
            logger.info("[EmbeddingFactory] EMBEDDING_TIERS empty, semantic search disabled.")
            return None
        tiers = [t.strip() for t in raw_tiers.split(",") if t.strip()]

        for tier in tiers:
            embedder = cls._try_tier(tier)
            if embedder is not None:
                if tier != tiers[0]:
                    logger.info("[EmbeddingFactory] Resolved via tier=%s", tier)
                return embedder

        logger.info(
            "[EmbeddingFactory] No embedding tier available. "
            "Semantic search disabled. Configure EMBEDDING_GGUF_MODEL, "
            "EMBEDDING_LOCAL_URL, or EMBEDDING_PROVIDER."
        )
        return None

    @classmethod
    def _try_tier(cls, tier: str) -> BaseEmbedder | None:
        if tier == "gguf":
            return cls._tier_gguf()
        if tier == "local":
            return cls._tier_local_http()
        if tier == "remote":
            return cls._tier_remote()
        logger.warning("[EmbeddingFactory] Unknown tier '%s', skipping", tier)
        return None

    # ---- tier implementations -----------------------------------------------

    @classmethod
    def _tier_gguf(cls) -> BaseEmbedder | None:
        model_path = _svc("EMBEDDING_GGUF_MODEL")
        if not model_path:
            return None
        try:
            import llama_cpp  # noqa: F401
            logger.info("[EmbeddingFactory] Tier=gguf, model=%s", model_path)
            return LocalEmbedder(model_path=model_path)
        except ImportError:
            logger.debug("[EmbeddingFactory] Tier=gguf skipped (llama_cpp not installed)")
            return None

    @classmethod
    def _tier_local_http(cls) -> BaseEmbedder | None:
        url = _svc("EMBEDDING_LOCAL_URL")
        if not url:
            return None
        api_key = _svc("EMBEDDING_LOCAL_API_KEY") or "lm-studio"
        model = _svc("EMBEDDING_LOCAL_MODEL") or "text-embedding-nomic-embed-text-v1.5"
        logger.info("[EmbeddingFactory] Tier=local, url=%s, model=%s", url, model)
        return GenericOpenAIEmbedder(
            api_key=api_key,
            base_url=url,
            model=model,
        )

    @classmethod
    def _tier_remote(cls) -> BaseEmbedder | None:
        base_url = _svc("EMBEDDING_BASE_URL")
        if not base_url:
            return None
        model = _svc("CUSTOM_EMBEDDING_MODEL") or _svc("EMBEDDING_MODEL")
        api_key = _svc("EMBEDDING_API_KEY")
        dim_val = _svc("EMBEDDING_DIMENSIONS")
        dims = int(dim_val) if dim_val else settings.EMBEDDING_DIMENSIONS
        return GenericOpenAIEmbedder(
            api_key=api_key, base_url=base_url, model=model, dimensions=dims,
        )

    @classmethod
    def _create_custom_embedding(cls, model_name: str) -> BaseEmbedder:
        prefix = "custom-embedding-" if model_name.startswith("custom-embedding-") else "custom-"
        parts = model_name[len(prefix):].split("-", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid custom model ID: {model_name}")
        actual_model = parts[1]
        base_url = _svc("EMBEDDING_BASE_URL")
        api_key = _svc("EMBEDDING_API_KEY")
        dim_val = _svc("EMBEDDING_DIMENSIONS")
        if not api_key:
            raise ValueError(f"Custom embedding requires EMBEDDING_API_KEY")
        dims = int(dim_val) if dim_val else 1536
        return GenericOpenAIEmbedder(
            api_key=api_key, base_url=base_url, model=actual_model, dimensions=dims,
        )

    @classmethod
    def reset_cache(cls) -> None:
        with cls._lock:
            cls._instances.clear()
