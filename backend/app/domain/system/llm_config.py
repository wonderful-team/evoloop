import logging
from app.domain.system.service import SystemConfigService
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class LLMConfigService:
    
    @staticmethod
    async def validate_connection(provider: str, base_url: str, model: str, api_key: str = None) -> bool:
        """
        Pre-flight check: Validates that the LLM can actually generate text.
        """
        try:
            # Create temporary LLM
            # We assume OpenAI compatible for now (provider check can expand later)
            llm = ChatOpenAI(
                api_key=api_key or "dummy",
                base_url=base_url,
                model=model,
                temperature=0,
                max_tokens=5
            )

            # Test invocation
            # Use invoke instead of predict for modern LangChain
            response = await llm.ainvoke("Ping")
            if not response or not response.content:
                 raise ValueError("Empty response from LLM")
            
            return True, response.content
        except Exception as e:
            logger.error(f"LLM Validation Failed: {e}")
            raise e

    @staticmethod
    async def applied_llm_config(
        provider: str, 
        base_url: str, 
        model: str, 
        api_key: str = None
    ):
        """
        Updates System Config for LLM.
        Non-destructive logic (unlike Embeddings).
        """
        
        # 1. Validate
        await LLMConfigService.validate_connection(provider, base_url, model, api_key)
        
        # 2. Update Config
        SystemConfigService.set_value("LLM_PROVIDER", provider)
        SystemConfigService.set_value("LLM_BASE_URL", base_url)
        SystemConfigService.set_value("LLM_MODEL", model)
        if api_key:
            SystemConfigService.set_value("LLM_API_KEY", api_key)
            
        logger.info(f"LLM Configuration updated to use {model} at {base_url}")
