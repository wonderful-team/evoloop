from app.core.config import settings
from app.domain.codebase.indexing.base import BaseEmbedder
from app.domain.codebase.indexing.vectors.ollama_embedder import OllamaEmbedder
from app.domain.codebase.indexing.vectors.openai_embedder import GenericOpenAIEmbedder
from app.domain.system.service import SystemConfigService


class EmbedderFactory:
    @staticmethod
    def get_embedder() -> BaseEmbedder:
        """
        Factory to create the configured Embedder.
        Priority:
        1. System Config (DB)
        2. Environment Variables (Settings)
        """
        # 1. Try DB Config
        provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")

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
                 return GenericOpenAIEmbedder(api_key=api_key, base_url=base_url, model=model_name, dimensions=dimensions)
            else:
                 # Default OpenAI
                 return GenericOpenAIEmbedder(
                     api_key=settings.OPENAI_API_KEY,
                     base_url=settings.OPENAI_BASE_URL,
                     model=settings.EMBEDDING_MODEL_NAME,
                     dimensions=dimensions
                 )

        # 2. DB Config Exists
        if provider == "openai" or provider == "generic" or provider == "local":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL") or settings.OPENAI_BASE_URL
            model = SystemConfigService.get_value("EMBEDDING_MODEL") or settings.EMBEDDING_MODEL_NAME
            api_key = SystemConfigService.get_value("EMBEDDING_API_KEY") or settings.OPENAI_API_KEY
            # Robust integer parsing
            dim_val = SystemConfigService.get_value("EMBEDDING_DIMENSIONS")
            dimensions = int(dim_val) if dim_val else settings.EMBEDDING_DIMENSIONS

            return GenericOpenAIEmbedder(api_key=api_key, base_url=base_url, model=model, dimensions=dimensions)

        elif provider == "ollama":
            base_url = SystemConfigService.get_value("EMBEDDING_BASE_URL") or "http://localhost:11434"
            model = SystemConfigService.get_value("EMBEDDING_MODEL") or "nomic-embed-text"
            return OllamaEmbedder(base_url=base_url, model=model)

        else:
            raise ValueError(f"Unknown Embedding Provider: {provider}")
