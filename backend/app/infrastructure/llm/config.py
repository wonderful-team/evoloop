import json
import logging

from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class LLMConfigService:
    @staticmethod
    async def validate_connection(
        provider: str,
        base_url: str,
        model: str,
        api_key: str = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """
        Pre-flight check: Validates that the LLM can actually generate text.
        """
        # 1. Load custom headers from database
        from app.infrastructure.config.service import SystemConfigService

        db_headers_str = SystemConfigService.get_value("LLM_HEADERS", "{}")
        try:
            final_headers = json.loads(db_headers_str) if db_headers_str else {}
        except json.JSONDecodeError:
            final_headers = {}

        # 2. Merge with explicit headers passed to validation (e.g. from UI testing form)
        if headers:
            final_headers.update(headers)

        if provider == "anthropic" or "api/anthropic" in (base_url or ""):
            from app.infrastructure.llm.anthropic_adapter import (
                CompatibleChatAnthropic,
            )

            # Anthropic SDK automatically appends /v1/messages.
            # Strip trailing /v1 to avoid double path (e.g. /coding/v1/v1/messages).
            normalized = base_url.rstrip("/")
            if normalized.endswith("/v1"):
                normalized = normalized[:-3]

            llm = CompatibleChatAnthropic(
                api_key=api_key,
                base_url=normalized,
                model_name=model,
                temperature=0,
                max_tokens=5,
                streaming=False,
                # Auto-detect fixes based on URL similar to factory.py
                fix_tool_args_list="bigmodel.cn" in (base_url or ""),
            )
        else:
            # We assume OpenAI compatible for now (provider check can expand later)
            from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

            llm = AdaptiveChatOpenAI(
                api_key=api_key or "dummy",
                base_url=base_url,
                model=model,
                temperature=0,
                max_tokens=5,
                default_headers=final_headers if final_headers else None,
            )

        # Test invocation
        # For thinking/reasoning models, the content might be empty if max_tokens is small
        # and it only generated thinking/reasoning tokens.
        # We use stream to confirm connectivity by checking if any chunk contains text/reasoning.
        content = ""
        async for chunk in llm.astream("Ping"):
            content += chunk.content
            # Capture reasoning_content from patched additional_kwargs if present
            reasoning = chunk.additional_kwargs.get("reasoning_content") or chunk.additional_kwargs.get("thinking")
            if reasoning:
                content += reasoning
            if len(content) > 100:
                break

        if not content:
            raise ValueError("Empty response from LLM")

        return True, content

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
