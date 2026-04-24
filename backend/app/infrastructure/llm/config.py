import logging

from langchain_openai import ChatOpenAI

from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class LLMConfigService:
    @staticmethod
    async def validate_connection(provider: str, base_url: str, model: str, api_key: str = None) -> tuple[bool, str]:
        """
        Pre-flight check: Validates that the LLM can actually generate text.
        """
        try:
            if provider in ["anthropic", "kimi"] or "api/anthropic" in (base_url or ""):
                from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic

                llm = CompatibleChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model,
                    temperature=0,
                    max_tokens=5,
                    streaming=False,
                    # Auto-detect fixes based on URL similar to factory.py
                    fix_tool_args_list="bigmodel.cn" in (base_url or ""),
                )
            else:
                # We assume OpenAI compatible for now (provider check can expand later)
                llm = ChatOpenAI(
                    api_key=api_key or "dummy",
                    base_url=base_url,
                    model=model,
                    temperature=0,
                    max_tokens=5,
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
        vision_model: str = None,
        vision_base_url: str = None,
        vision_api_key: str = None,
        vision_provider_type: str = None,
        api_key: str = None,
    ):
        """
        Updates System Config for LLM.
        Non-destructive logic (unlike Embeddings).
        
        Supports independent Vision endpoint configuration (e.g., local VLM).
        """

        # 1. Validate main LLM connection
        await LLMConfigService.validate_connection(provider, base_url, model, api_key)

        # 2. Validate Vision connection if independent endpoint is provided
        if vision_base_url:
            vision_provider = vision_provider_type or provider
            vision_key = vision_api_key or api_key
            await LLMConfigService.validate_connection(
                vision_provider, vision_base_url, vision_model or model, vision_key
            )

        # 3. Update Config
        SystemConfigService.set_value("LLM_PROVIDER", provider)
        SystemConfigService.set_value("LLM_BASE_URL", base_url)
        SystemConfigService.set_value("LLM_MODEL", model)

        if vision_model:
            SystemConfigService.set_value("VISION_MODEL", vision_model)

        if vision_base_url:
            SystemConfigService.set_value("VISION_BASE_URL", vision_base_url)

        if vision_api_key:
            SystemConfigService.set_value("VISION_API_KEY", vision_api_key)

        if vision_provider_type:
            SystemConfigService.set_value("VISION_PROVIDER_TYPE", vision_provider_type)

        if api_key:
            SystemConfigService.set_value("LLM_API_KEY", api_key)

        logger.info(f"LLM Configuration updated to use {model} at {base_url}")
        if vision_base_url:
            logger.info(f"Vision Configuration updated to use {vision_model or model} at {vision_base_url}")
