import json
import logging

from app.infrastructure.llm.thinking_adapter import (
    detect_model_family,
    extract_reasoning_from_kwargs,
)

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

        if provider == "anthropic" or detect_model_family(model, base_url) == "anthropic":
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
                fix_tool_args_list=False,
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
            reasoning = extract_reasoning_from_kwargs(chunk.additional_kwargs)
            if reasoning:
                content += reasoning
            if len(content) > 100:
                break

        if not content:
            raise ValueError("Empty response from LLM")

        return True, content
