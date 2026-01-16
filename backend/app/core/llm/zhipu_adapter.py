from typing import Any
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
    # If langchain_anthropic is not installed, we can't do anything. 
    # But factory checks for import.
    pass


class ZhipuChatAnthropic(ChatAnthropic):
    """
    Adapter for Zhipu AI (GLM-4) using Anthropic Protocol.
    Fixes known compatibility issues like list-wrapped tool arguments.
    """
    
    def _format_output(self, data: Any, **kwargs: Any) -> ChatResult:
        data_dict = data.model_dump()
        content = data_dict["content"]

        # --- Zhipu Fix Start ---
        # Zhipu sometimes returns tool arguments as a list of dicts instead of a dict.
        # Example: "input": [{"path": "..."}] instead of "input": {"path": "..."}
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use":
                    inp = block.get("input")
                    if isinstance(inp, list) and inp and isinstance(inp[0], dict):
                        # Unwrap the list
                        block["input"] = inp[0]
                    elif isinstance(inp, list) and not inp:
                         block["input"] = {}
        # --- Zhipu Fix End ---

        # Remove citations if they are None (Copied from original logic)
        for block in content:
            if (
                isinstance(block, dict)
                and "citations" in block
                and block["citations"] is None
            ):
                block.pop("citations")
            if (
                isinstance(block, dict)
                and block.get("type") == "thinking"
                and "text" in block
                and block["text"] is None
            ):
                block.pop("text")

        llm_output = {
            k: v for k, v in data_dict.items() if k not in ("content", "role", "type")
        }
        if "model" in llm_output and "model_name" not in llm_output:
            llm_output["model_name"] = llm_output["model"]
        
        # Construct AIMessage
        if (
            len(content) == 1
            and content[0]["type"] == "text"
            # and not content[0].get("citations") # Optional check matches original
        ):
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
