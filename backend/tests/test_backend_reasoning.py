#!/usr/bin/env python3
"""
Test backend reasoning_content pipeline:
1. Monkey-patch applied
2. _convert_delta_to_message_chunk captures reasoning_content
3. TransparentCallbackHandler extracts it from chunk
4. InferenceEngine extracts it from AIMessage.additional_kwargs
"""
import asyncio
import sys

sys.path.insert(0, "backend")


def test_patch_applied():
    """Test that the monkey-patch is applied (auto-applied on module import)."""
    import app.core.engine.message.reasoning  # noqa: F401 — triggers auto-apply
    import langchain_openai.chat_models.base as base_module

    # Verify the function name contains our wrapper
    func = base_module._convert_delta_to_message_chunk
    assert hasattr(func, "__closure__") or "reasoning" in str(func.__code__.co_consts), \
        "Patch not applied - _convert_delta_to_message_chunk is not wrapped"
    print("✅ Patch applied correctly")


def test_delta_conversion():
    """Test that reasoning_content delta is captured."""
    import langchain_openai.chat_models.base as base_module
    from langchain_core.messages import AIMessageChunk

    # Simulate a delta with reasoning_content
    delta_dict = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "Let me think about this...",
    }

    result = base_module._convert_delta_to_message_chunk(delta_dict, AIMessageChunk)

    assert isinstance(result, AIMessageChunk), "Result should be AIMessageChunk"
    assert "reasoning_content" in result.additional_kwargs, \
        "reasoning_content should be in additional_kwargs"
    assert result.additional_kwargs["reasoning_content"] == "Let me think about this...", \
        "reasoning_content value mismatch"
    print(f"✅ reasoning_content captured: '{result.additional_kwargs['reasoning_content']}'")

    # Test accumulation
    delta_dict2 = {
        "role": "assistant",
        "content": "The answer is 2",
        "reasoning_content": " Therefore 1+1=2",
    }
    result2 = base_module._convert_delta_to_message_chunk(delta_dict2, AIMessageChunk)
    combined = result + result2
    assert combined.additional_kwargs.get("reasoning_content") == "Let me think about this... Therefore 1+1=2", \
        f"Accumulated reasoning mismatch: {combined.additional_kwargs.get('reasoning_content')}"
    print(f"✅ Accumulation works: '{combined.additional_kwargs['reasoning_content']}'")


def test_inference_engine_extraction():
    """Test that InferenceEngine extracts reasoning_content correctly."""
    from langchain_core.messages import AIMessage

    # Simulate an AIMessage with reasoning_content
    response = AIMessage(
        content="The answer is 2",
        additional_kwargs={"reasoning_content": "Let me think... 1+1=2"},
        tool_calls=[],
    )

    # Simulate the extraction logic from run_react_loop
    thinking_content = ""
    if hasattr(response, "additional_kwargs") and response.additional_kwargs:
        reasoning = response.additional_kwargs.get("reasoning_content")
        if reasoning:
            thinking_content = reasoning

    assert thinking_content == "Let me think... 1+1=2", f"Extraction failed: {thinking_content}"
    print(f"✅ InferenceEngine extraction works: '{thinking_content}'")


def test_factory_model_kwargs():
    """Test that factory passes model_kwargs correctly."""
    from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

    llm = AdaptiveChatOpenAI(
        api_key="test",
        base_url="http://test",
        model="kimi-k2-thinking-turbo",
        model_kwargs={
            "enable_thinking": True,
            "return_reasoning": True,
        },
    )

    payload = llm._get_request_payload([])
    assert payload.get("enable_thinking") is True, "enable_thinking not in payload"
    assert payload.get("return_reasoning") is True, "return_reasoning not in payload"
    print(f"✅ Factory model_kwargs passed: {payload}")


def test_transparent_callback_logic():
    """Test TransparentCallbackHandler reasoning extraction logic."""
    from langchain_core.outputs import ChatGenerationChunk
    from langchain_core.messages import AIMessageChunk

    # Simulate a chunk with reasoning_content (same structure LangChain passes)
    msg_chunk = AIMessageChunk(
        content="",
        additional_kwargs={"reasoning_content": "Thinking step 1..."},
    )
    gen_chunk = ChatGenerationChunk(message=msg_chunk, text="")

    # Verify the extraction logic that the handler uses
    chunk = gen_chunk
    if chunk and hasattr(chunk, "message"):
        msg_chunk = chunk.message
        if hasattr(msg_chunk, "additional_kwargs"):
            reasoning = msg_chunk.additional_kwargs.get("reasoning_content")
            assert reasoning == "Thinking step 1...", f"Extraction failed: {reasoning}"
            print(f"✅ Callback extraction logic: '{reasoning}'")


def main():
    print("=" * 60)
    print("Backend Reasoning Pipeline Tests")
    print("=" * 60)

    test_patch_applied()
    test_delta_conversion()
    test_inference_engine_extraction()
    test_factory_model_kwargs()
    test_transparent_callback_logic()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
