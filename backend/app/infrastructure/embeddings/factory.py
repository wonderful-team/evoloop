import logging
import threading

from app.core.config import settings
from app.infrastructure.config import SystemConfigService
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.local import LocalEmbedder
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

logger = logging.getLogger(__name__)


class EmbedderFactory:
    """Creates and caches the configured Embedder.

    The embedder instance is cached so that repeated calls within the
    same process reuse the same underlying model, avoiding redundant
    ~3-5s model loading from disk (especially in Huey worker tasks).

    Thread-safety:
        A threading.Lock protects the shared cache. The expensive embedder
        creation happens outside the lock so that the asyncio event loop is
        not blocked while the model is being loaded.
    """

    _instances: dict[str, BaseEmbedder] = {}
    _default_key: str = "__default__"
    _lock = threading.Lock()

    @classmethod
    def get_embedder(cls, model_name: str | None = None) -> BaseEmbedder:
        """
        Factory to create the configured Embedder.
        Priority:
        1. Explicit model_name (if provided)
        2. System Config (DB)
        3. Environment Variables (Settings)

        Results are cached by model_name so repeated calls in the same
        process share one embedder instance (and its in-memory model).
        """
        cache_key = model_name or cls._default_key

        with cls._lock:
            cached = cls._instances.get(cache_key)
        if cached is not None:
            return cached

        # Create the embedder outside the lock so the asyncio event loop is
        # not blocked by potentially expensive model initialization.
        embedder = cls._create_embedder(model_name, cache_key)

        with cls._lock:
            if cache_key not in cls._instances:
                cls._instances[cache_key] = embedder
            return cls._instances[cache_key]

    @classmethod
    def _create_embedder(cls, model_name: str | None, cache_key: str) -> BaseEmbedder:
        """Resolve and instantiate the configured embedder (no cache lookup)."""
        # 0. Resolution: if not provided, fetch from DB
        if not model_name:
            try:
                model_name = SystemConfigService.get_value("EMBEDDING_MODEL")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        # 1. Auto-detect custom embedding model by ID prefix
        if model_name and (model_name.startswith("custom-embedding-") or model_name.startswith("custom-")):
            prefix = "custom-embedding-" if model_name.startswith("custom-embedding-") else "custom-"
            parts = model_name[len(prefix):].split("-", 1)

            if len(parts) >= 2:
                provider = parts[0]
                actual_model = parts[1]
                logger.debug(f"[EmbeddingFactory] Resolved custom embedding: provider={provider}, model={actual_model} (ID: {model_name})")

                base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
                api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")
                dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")

                if not api_key:
                    raise ValueError(f"Custom embedding '{actual_model}' requires EMBEDDING_API_KEY in configuration")

                dimensions = int(dim_val) if dim_val else 1536

                return GenericOpenAIEmbedder(
                    api_key=api_key,
                    base_url=base_url,
                    model=actual_model,
                    dimensions=dimensions
                )

        # 2. Try DB Config (handle case where DB tables don't exist yet)
        try:
            provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"Could not read EMBEDDING_PROVIDER from DB (tables may not exist yet): {e}")
            provider = None

        # 3. If no provider configured, fall back to local embedder only when
        # explicitly enabled. Local embeddings are CPU-heavy and can make the
        # whole system unresponsive, so they are opt-in via EMBEDDING_ENABLED.
        if not provider:
            if not settings.EMBEDDING_ENABLED:
                logger.info(
                    "Embedding provider not configured and EMBEDDING_ENABLED is false. "
                    "Semantic search disabled; set a third-party embedding provider or "
                    "set EMBEDDING_ENABLED=true to enable local embeddings."
                )
                return None
            try:
                import sentence_transformers  # noqa: F401
                logger.info("Embedding provider not configured but EMBEDDING_ENABLED is true. Falling back to LocalEmbedder (SentenceTransformers).")
                return LocalEmbedder()
            except ImportError:
                logger.warning(
                    "Embedding provider not configured and sentence_transformers is not installed. "
                    "Semantic search will be disabled until a provider is configured."
                )
                return None

        # 4. DB Config Exists
        if provider == "openai" or provider == "generic":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
            model = SystemConfigService.get_value("CUSTOM_EMBEDDING_MODEL") or SystemConfigService.get_value("EMBEDDING_MODEL")
            api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")
            dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")
            dimensions = int(dim_val) if dim_val else settings.EMBEDDING_DIMENSIONS

            return GenericOpenAIEmbedder(
                api_key=api_key,
                base_url=base_url,
                model=model,
                dimensions=dimensions
            )

        elif provider == "local":
            if not settings.EMBEDDING_ENABLED:
                logger.info(
                    "Embedding provider configured as 'local' but EMBEDDING_ENABLED is false. "
                    "Semantic search disabled."
                )
                return None
            try:
                import sentence_transformers  # noqa: F401
                logger.info("Embedding provider configured as 'local' and EMBEDDING_ENABLED is true. Using LocalEmbedder (SentenceTransformers).")
                return LocalEmbedder()
            except ImportError:
                logger.warning(
                    "Embedding provider configured as 'local' but sentence_transformers is not installed. "
                    "Semantic search will be disabled."
                )
                return None

        elif provider == "ollama":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL") or "http://localhost:11434"
            model = SystemConfigService.get_value("EMBEDDING_MODEL") or "nomic-embed-text"
            return OllamaEmbedder(base_url=base_url, model=model)

        elif provider == "lm-studio" or provider == "lmstudio":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL") or "http://localhost:1234/v1"
            model = SystemConfigService.get_value("EMBEDDING_MODEL") or "text-embedding-nomic-embed-text-v1.5"
            api_key = SystemConfigService.get_value("EMBEDDING_API_KEY") or "lm-studio"
            dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")
            dimensions = int(dim_val) if dim_val else settings.EMBEDDING_DIMENSIONS

            return GenericOpenAIEmbedder(
                api_key=api_key,
                base_url=base_url,
                model=model,
                dimensions=dimensions
            )

        else:
            raise ValueError(f"Unknown Embedding Provider: {provider}")

    @classmethod
    def reset_cache(cls) -> None:
        """Clear the cached embedder instance (useful for testing)."""
        with cls._lock:
            cls._instances.clear()
