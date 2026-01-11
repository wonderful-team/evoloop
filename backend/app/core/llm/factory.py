from typing import Optional
from app.core.llm.adaptive import AdaptiveChatOpenAI
from app.core.config import settings


class LLMFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    """
    
    @staticmethod
    def create_llm(model_name: Optional[str] = None, temperature: float = 0.7) -> AdaptiveChatOpenAI:
        """
        Create a standard ChatOpenAI instance.
        Prioritizes SystemConfig (Dynamic) > Settings (Env Checks).
        """
        from app.domain.system.service import SystemConfigService
        
        # 1. Fetch Config
        db_provider = SystemConfigService.get_value("LLM_PROVIDER")
        db_base_url = SystemConfigService.get_value("LLM_BASE_URL")
        db_model = SystemConfigService.get_value("LLM_MODEL")
        db_api_key = SystemConfigService.get_value("LLM_API_KEY")
        
        # 2. Resolve
        base_url = db_base_url or settings.OPENAI_BASE_URL
        api_key = db_api_key or settings.OPENAI_API_KEY
        final_model = model_name or db_model or settings.OPENAI_MODEL_NAME
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"LLM Config - Provider: {db_provider}, Base URL: {base_url}, Model: {final_model}")
        
        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=final_model,
            temperature=temperature,
            streaming=True
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm() -> AdaptiveChatOpenAI:
    return LLMFactory.create_llm()