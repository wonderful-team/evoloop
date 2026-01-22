import logging

from app.core.config import settings
from app.core.llm.adaptive import AdaptiveChatOpenAI

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    """

    @staticmethod
    def create_llm(model_name: str | None = None, temperature: float = 0.7) -> AdaptiveChatOpenAI:
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

        logger.info(f"LLM Config - Provider: {db_provider}, Base URL: {base_url}, Model: {final_model}")

        # Anthropic / Claude Protocol Support
        if db_provider == "anthropic" or "api/anthropic" in (base_url or ""):
            # Check for Zhipu GLM-4 (requires response patching)
            if "bigmodel.cn" in (base_url or ""):
                from app.core.llm.zhipu_adapter import ZhipuChatAnthropic

                return ZhipuChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=final_model,
                    temperature=temperature,
                    streaming=False,
                )

            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                api_key=api_key,
                base_url=base_url,
                model_name=final_model,
                temperature=temperature,
                streaming=False,  # Disable streaming to prevent httpx.ResponseNotRead on errors
            )

        # Default: OpenAI Compatible (Adaptive)
        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=final_model,
            temperature=temperature,
            streaming=True,
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm() -> AdaptiveChatOpenAI:
    return LLMFactory.create_llm()
