from typing import Any, Optional

try:
    from langchain_anthropic import ChatAnthropic

    try:
        from langchain_anthropic.chat_models import _create_usage_metadata
    except ImportError:
        # Fallback if _create_usage_metadata is not available or moved
        from langchain_core.messages.ai import UsageMetadata


        def _create_usage_metadata(usage: Any) -> UsageMetadata:
            return UsageMetadata(
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens
            )

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
    repair_history: bool = True
    clean_null_fields: bool = True

    def __init__(self, **kwargs: Any) -> None:
        # Extract custom fields first
        fix_tool_args_list = kwargs.pop("fix_tool_args_list", False)
        repair_history = kwargs.pop("repair_history", True)
        clean_null_fields = kwargs.pop("clean_null_fields", True)

        # Initialize parent (Pydantic model)
        super().__init__(**kwargs)

        # Set attributes AFTER parent initialization
        self.fix_tool_args_list = fix_tool_args_list
        self.repair_history = repair_history
        self.clean_null_fields = clean_null_fields

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.repair_history:
            from app.core.engine.message_utils import repair_message_history
            messages = repair_message_history(messages)
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.repair_history:
            from app.core.engine.message_utils import repair_message_history
            messages = repair_message_history(messages)
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
