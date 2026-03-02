import httpx
import logging

from langchain_anthropic import ChatAnthropic

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

logger = logging.getLogger(__name__)

from app.utils.async_utils import LoopBoundResource

# Global Shared HTTP Client for Connection Pooling (HTTP/2 enabled), per Event Loop
async def _close_client(client: httpx.AsyncClient):
    await client.aclose()

_HTTP_CLIENT_POOL = LoopBoundResource(
    factory=lambda: httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(60.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    ),
    cleanup=_close_client
)


class LLMFactory:
    """
    Factory for creating LLM instances with consistent configuration.
    """

    @staticmethod
    def create_llm(model_name: str | None = None, temperature: float = 0.3) -> AdaptiveChatOpenAI:
        """
        Create a standard ChatOpenAI instance.
        Prioritizes SystemConfig (Dynamic) > Settings (Env Checks).
        """
        from app.infrastructure.config.service import SystemConfigService

        # 1. Fetch Config
        provider = SystemConfigService.get_value("LLM_PROVIDER")
        base_url = SystemConfigService.get_value("LLM_BASE_URL")
        model_name = model_name or SystemConfigService.get_value("LLM_MODEL")
        api_key = SystemConfigService.get_value("LLM_API_KEY")

        logger.info(f"LLM Config - Provider: {provider}, Base URL: {base_url}, Model: {model_name}")

        # Anthropic / Claude Protocol Support (Zhipu, Kimi, etc.)
        if provider in ["anthropic", "kimi"] or "api/anthropic" in (base_url or ""):
            from app.infrastructure.llm.anthropic_adapter import CompatibleChatAnthropic

            # Check for Zhipu GLM-4 (requires response patching)
            if "bigmodel.cn" in (base_url or ""):
                return CompatibleChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    streaming=False,
                    fix_tool_args_list=True,
                    repair_history=True,
                )

            # Check for Kimi / Moonshot
            if any(domain in (base_url or "") for domain in ["moonshot.cn", "kimi.ai", "kimi.com"]):
                return CompatibleChatAnthropic(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    temperature=temperature,
                    streaming=False,
                    fix_tool_args_list=False,  # Kimi usually follows standard
                    repair_history=True,       # Most compatible APIs need history repair
                )

            return ChatAnthropic(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                streaming=False,  # Disable streaming to prevent httpx.ResponseNotRead on errors
            )

        # Default: OpenAI Compatible (Adaptive)
        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            streaming=True,
            http_async_client=_HTTP_CLIENT_POOL.get(),
        )

    @staticmethod
    def create_completion_client(
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7
    ):
        """
        Create a raw Completion client (Legacy/Text-Generation) for SSM/Flash Brain.
        Useful for endpoints that strictly use /v1/completions.
        """
        from langchain_openai import OpenAI
        return OpenAI(
            openai_api_key=api_key,
            openai_api_base=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=512
        )


# Global instance for easy import if needed, or prefer using Factory.create()
def get_default_llm(temperature: float = 0.3) -> AdaptiveChatOpenAI:
    return LLMFactory.create_llm(temperature=temperature)
