import logging
from functools import cached_property
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


try:
    from langchain_anthropic import ChatAnthropic

    try:
        from langchain_anthropic.chat_models import _create_usage_metadata
    except ImportError:
        # Fallback if _create_usage_metadata is not available or moved
        from langchain_core.messages.ai import UsageMetadata

        def _create_usage_metadata(usage: Any) -> UsageMetadata:
            return UsageMetadata(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)

    from langchain_anthropic.output_parsers import extract_tool_calls
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
except ImportError:
    # Fallback for testing/env without langchain-anthropic
    class ChatAnthropic:
        def __init__(self, **kwargs):
            self.__pydantic_fields_set__ = set()
            for k, v in kwargs.items(): setattr(self, k, v)

    class AIMessage:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)

    class ChatGeneration:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)

    class ChatResult:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)

    def extract_tool_calls(content):
        return []

    def _create_usage_metadata(usage):
        return None


class CompatibleChatAnthropic(ChatAnthropic):
    """
    Generic adapter for Anthropic-compatible protocols (Zhipu, Kimi, etc.)
    that might have slight deviations from the standard.
    """

    fix_tool_args_list: bool = False
    clean_null_fields: bool = True
    http_async_client: Any = None

    def __init__(self, **kwargs: Any) -> None:
        # Extract custom fields first
        fix_tool_args_list = kwargs.pop("fix_tool_args_list", False)
        clean_null_fields = kwargs.pop("clean_null_fields", True)
        http_async_client = kwargs.pop("http_async_client", None)

        # Initialize parent (Pydantic model)
        super().__init__(**kwargs)

        # Set attributes AFTER parent initialization
        self.fix_tool_args_list = fix_tool_args_list
        self.clean_null_fields = clean_null_fields
        self.http_async_client = http_async_client

    @cached_property
    def _async_client(self) -> anthropic.AsyncClient:
        if self.http_async_client:
            client_params = self._client_params
            return anthropic.AsyncClient(
                api_key=client_params["api_key"],
                base_url=client_params["base_url"],
                http_client=self.http_async_client,
            )
        return super()._async_client

    @cached_property
    def _client(self) -> anthropic.Client:
        # We don't have a sync pool easily, but we can default or use a dummy for now
        # Standard usage is async anyway.
        return super()._client

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _format_output(self, data: Any, **kwargs: Any) -> ChatResult:
        data_dict = data.model_dump()
        content = data_dict["content"]

        if self.fix_tool_args_list and isinstance(content, list):
            # Zhipu Fix: sometimes returns tool arguments as a list of dicts instead of a dict.
            for block in content:
                if block.get("type") == "tool_use":
                    inp = block.get("input")
                    if isinstance(inp, list) and inp and isinstance(inp[0], dict):
                        block["input"] = inp[0]
                    elif isinstance(inp, list) and not inp:
                        block["input"] = {}

        if self.clean_null_fields and isinstance(content, list):
            # Remove citations/thinking if they are None (Copied from original logic)
            for block in content:
                if isinstance(block, dict):
                    if block.get("citations") is None and "citations" in block:
                        block.pop("citations")
                    if (
                            block.get("type") == "thinking"
                            and block.get("text") is None
                            and "text" in block
                    ):
                        block.pop("text")

        llm_output = {
            k: v for k, v in data_dict.items() if k not in ("content", "role", "type")
        }
        if "model" in llm_output and "model_name" not in llm_output:
            llm_output["model_name"] = llm_output["model"]

        # Construct AIMessage
        if not content:
            msg = AIMessage(content="")
        elif len(content) == 1 and content[0].get("type") == "text":
            msg = AIMessage(content=content[0]["text"])
        elif any(block["type"] == "tool_use" for block in content):
            tool_calls = extract_tool_calls(content)

            # Manual fallback if library extraction fails but content has tool_use blocks
            if not tool_calls:
                manual_calls = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        manual_calls.append({
                            "name": block.get("name"),
                            "args": block.get("input") or {},
                            "id": block.get("id"),
                            "type": "tool_call" # internal marker
                        })
                if manual_calls:
                    tool_calls = manual_calls

            msg = AIMessage(
                content=content,
                tool_calls=tool_calls,
            )
        else:
            msg = AIMessage(content=content)

        msg.usage_metadata = _create_usage_metadata(data.usage)
        return ChatResult(
            generations=[ChatGeneration(message=msg)],
            llm_output=llm_output,
        )
