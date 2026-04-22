import logging

from app.core.config import settings
from app.infrastructure.config import SystemConfigService
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

logger = logging.getLogger(__name__)


class EmbedderFactory:
    @staticmethod
    def get_embedder(model_name: str | None = None) -> BaseEmbedder:
        """
        Factory to create the configured Embedder.
        Priority:
        1. Explicit model_name (if provided)
        2. System Config (DB)
        3. Environment Variables (Settings)
        
        Args:
            model_name: Optional model identifier. Supports custom-embedding-{provider}-{model} format.
        """
        # 0. Resolution: if not provided, fetch from DB
        if not model_name:
            try:
                model_name = SystemConfigService.get_value("EMBEDDING_MODEL")
            except Exception:
                pass

        # 1. 🔍 Auto-detect custom embedding model by ID prefix
        if model_name and (model_name.startswith("custom-embedding-") or model_name.startswith("custom-")):
            # Standard IDs are custom-embedding-{provider}-{model}
            # Compatible with LLM style custom-{provider}-{model}
            prefix = "custom-embedding-" if model_name.startswith("custom-embedding-") else "custom-"
            parts = model_name[len(prefix):].split("-", 1)
            
            if len(parts) >= 2:
                provider = parts[0]
                actual_model = parts[1]
                logger.debug(f"[EmbeddingFactory] Resolved custom embedding: provider={provider}, model={actual_model} (ID: {model_name})")

                # Get custom embedding config from SystemConfig
                base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
                api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")
                dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")
                
                if not api_key:
                    raise ValueError(f"Custom embedding '{actual_model}' requires EMBEDDING_API_KEY in configuration")

                dimensions = int(dim_val) if dim_val else 1536 # Default to safe standard dimension if missing
                
                return GenericOpenAIEmbedder(
                    api_key=api_key,
                    base_url=base_url,
                    model=actual_model,
                    dimensions=dimensions
                )

        # 1. Try DB Config (handle case where DB tables don't exist yet)
        try:
            provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
        except Exception as e:
            logger.debug(f"Could not read EMBEDDING_PROVIDER from DB (tables may not exist yet): {e}")
            provider = None

        if not provider:
            # No explicit provider configured and no DB config.
            # Low priority warning instead of error to allow OpenAPI export and setup
            warning_msg = "Embedding provider not configured. Some features may be disabled until configured via System Settings."
            logger.warning(warning_msg)
            # Return None or a dummy to allow startup
            return None # type: ignore

        # 2. DB Config Exists
        if provider == "openai" or provider == "generic" or provider == "local":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
            # 优先从 CUSTOM_EMBEDDING_MODEL 获取，避免 ID 冲突
            model = SystemConfigService.get_value("CUSTOM_EMBEDDING_MODEL") or SystemConfigService.get_value("EMBEDDING_MODEL")
            api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")
            # Robust integer parsing
            dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")
            dimensions = int(dim_val) if dim_val else settings.EMBEDDING_DIMENSIONS

            return GenericOpenAIEmbedder(
                api_key=api_key,
                base_url=base_url,
                model=model,
                dimensions=dimensions
            )

        elif provider == "ollama":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL") or "http://localhost:11434"
            model = SystemConfigService.get_value("EMBEDDING_MODEL") or "nomic-embed-text"
            return OllamaEmbedder(base_url=base_url, model=model)

        elif provider == "lm-studio" or provider == "lmstudio":
            # LM Studio uses OpenAI-compatible API
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
