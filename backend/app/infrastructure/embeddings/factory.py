import logging

from app.core.config import settings
from app.infrastructure.config import SystemConfigService
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

logger = logging.getLogger(__name__)


class EmbedderFactory:
    @staticmethod
    def get_embedder() -> BaseEmbedder:
        """
        Factory to create the configured Embedder.
        Priority:
        1. System Config (DB)
        2. Environment Variables (Settings)
        """
        # 1. Try DB Config (handle case where DB tables don't exist yet)
        try:
            provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
        except Exception as e:
            logger.debug(f"Could not read EMBEDDING_PROVIDER from DB (tables may not exist yet): {e}")
            provider = None

        if not provider:
            # Fallback to config.py defaults
            # We map default settings to a "provider" logic
            # Assuming settings defaults to "openai" or "generic" depending on base_url
            dimensions = settings.EMBEDDING_DIMENSIONS
            if "localhost" in settings.OPENAI_BASE_URL and "v1" in settings.OPENAI_BASE_URL:
                # Likely LMStudio/Local, but using OpenAI protocol
                model_name = settings.EMBEDDING_MODEL_NAME
                base_url = settings.OPENAI_BASE_URL
                api_key = settings.OPENAI_API_KEY
                return GenericOpenAIEmbedder(
                    api_key=api_key,
                    base_url=base_url,
                    model=model_name,
                    dimensions=dimensions,
                )
            else:
                # Default OpenAI
                return GenericOpenAIEmbedder(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_BASE_URL,
                    model=settings.EMBEDDING_MODEL_NAME,
                    dimensions=dimensions,
                )

        # 2. DB Config Exists
        if provider == "openai" or provider == "generic" or provider == "local":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL")
            model = SystemConfigService.get_value("EMBEDDING_MODEL")
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
