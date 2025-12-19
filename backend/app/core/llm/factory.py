from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.core.config import settings


class LLMFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    """

    @staticmethod
    def create_llm(model_name: Optional[str] = None, temperature: float = 0.7) -> BaseChatModel:
        """
        Create a standard ChatOpenAI instance.
        """
        return ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=model_name or settings.OPENAI_MODEL_NAME,
            temperature=temperature
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm() -> BaseChatModel:
    return LLMFactory.create_llm()
