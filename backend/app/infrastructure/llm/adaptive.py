import inspect
import logging
from typing import Any, AsyncGenerator, Union, get_args, get_origin

import openai
from pydantic import BaseModel, Field, create_model

from app.core.engine.message.native_classes import AIMessageChunk
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def _generate_args_schema_from_signature(func) -> type[BaseModel] | None:
    """Auto-generate a Pydantic args schema from a function's signature.

    This is used when a tool does not have an explicit ``args_schema`` —
    without it the LLM receives an empty ``{"type": "object", "properties": {}}``
    schema and has to guess the parameters, which frequently leads to missing
    or empty values for required fields like ``reason``.
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return None

    fields: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "config"):
            continue
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else Any
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[param_name] = (annotation, default)

    if not fields:
        return None

    func_name = getattr(func, "__name__", "Tool")
    model_name = f"{func_name}_AutoSchema"
    return create_model(model_name, **fields)


class AdaptiveRetryState(BaseModel):
    """Encapsulates the state and logic for an adaptive retry attempt."""
    attempt: int = 0
    max_retries: int = 3
    current_max_tokens: int
    current_temperature: float

    def next_state(self) -> "AdaptiveRetryState":
        """Calculates the next state with decayed parameters."""
        decay = 0.8 if self.attempt == 0 else (0.6 if self.attempt == 1 else 0.5)
        return AdaptiveRetryState(
            attempt=self.attempt + 1,
            max_retries=self.max_retries,
            current_max_tokens=int(self.current_max_tokens * decay),
            current_temperature=max(self.current_temperature - 0.2, 0.0)
        )

    @property
    def can_retry(self) -> bool:
        return self.attempt < self.max_retries


class AdaptiveChatOpenAI:
    """
    A robust, native, SDK-free ChatOpenAI wrapper that implements DeepCode's 'Adaptive Token Strategy'.
    """

    retry_max_tokens_base: int = 32000
    adaptive_retries: int = 3

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.3,
        streaming: bool = True,
        max_tokens: int | None = None,
        http_async_client: Any = None,
        extra_body: dict | None = None,
        default_headers: dict | None = None,
        **kwargs: Any
    ):
        self.model = model
        self.temperature = temperature
        self.streaming = streaming
        self.max_tokens = max_tokens
        self.extra_body = extra_body or {}
        self.default_headers = default_headers or {}
        self._tools = []

        # Create native async OpenAI client
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_async_client,
            default_headers=default_headers
        )

    def bind_tools(self, tools: list[Any]) -> "AdaptiveChatOpenAI":
        self._tools = []
        for t in tools:
            # Use explicit args_schema if provided, otherwise auto-generate
            # from the function signature so the LLM sees proper parameters.
            args_schema = getattr(t, "args_schema", None)
            if args_schema is None:
                args_schema = _generate_args_schema_from_signature(t.func)

            t_schema = {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": args_schema.model_json_schema() if args_schema else {"type": "object", "properties": {}}
                }
            }
            # Remove Pydantic v2 internal noise fields, but keep $defs
            # which is required for $ref references in nested models.
            if "parameters" in t_schema["function"]:
                params = t_schema["function"]["parameters"]
                params.pop("title", None)
                params.pop("additionalProperties", None)
            self._tools.append(t_schema)
        return self

    async def astream(self, messages: list[Any], config: dict = None, **kwargs: Any) -> AsyncGenerator[AIMessageChunk, None]:
        from app.core.engine.callbacks.bridge import (
            _get_callbacks, _get_run_id, _get_metadata,
            emit_llm_start, emit_llm_new_token, emit_llm_end,
        )
        from app.core.engine.message.native_classes import AIMessage

        callbacks = _get_callbacks(config)
        run_id = _get_run_id(config)
        metadata = _get_metadata(config)

        state = AdaptiveRetryState(
            current_max_tokens=self.max_tokens or self.retry_max_tokens_base,
            current_temperature=self.temperature if self.temperature is not None else 0.7,
            max_retries=self.adaptive_retries
        )

        # Standardize messages to API dict structure
        api_messages = []
        for m in messages:
            if isinstance(m, dict):
                api_messages.append(m)
            else:
                role = "assistant" if m.type == "ai" else (m.type if m.type in ("system", "tool") else "user")
                msg_dict = {"role": role, "content": m.content}
                if role == "tool" and m.tool_call_id:
                    msg_dict["tool_call_id"] = m.tool_call_id
                elif role == "assistant" and m.tool_calls:
                    msg_dict["tool_calls"] = m.tool_calls
                api_messages.append(msg_dict)

        if callbacks:
            await emit_llm_start(callbacks, run_id, metadata)

        while True:
            try:
                req_params = {
                    "model": self.model,
                    "messages": api_messages,
                    "temperature": state.current_temperature,
                    "stream": True,
                    "extra_body": self.extra_body,
                }
                if state.current_max_tokens:
                    req_params["max_tokens"] = state.current_max_tokens
                if self._tools:
                    req_params["tools"] = self._tools

                if state.attempt > 0:
                    logger.info(f"🔄 Adaptive Retry {state.attempt}/{state.max_retries}: {state}")

                stream = await self.client.chat.completions.create(**req_params)

                accumulated: AIMessageChunk | None = None
                accumulated_reasoning: list[str] = []
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None) or ""
                    reasoning = getattr(delta, "reasoning_content", None) or ""

                    additional_kwargs = {}
                    if reasoning:
                        additional_kwargs["reasoning_content"] = reasoning
                        additional_kwargs["thinking"] = reasoning
                        accumulated_reasoning.append(reasoning)

                    tool_calls = []
                    if getattr(delta, "tool_calls", None):
                        for tc in delta.tool_calls:
                            tool_calls.append({
                                "index": tc.index,
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "args": tc.function.arguments if tc.function else ""
                            })

                    msg_chunk = AIMessageChunk(
                        content=content,
                        tool_calls=tool_calls,
                        additional_kwargs=additional_kwargs
                    )

                    if callbacks:
                        await emit_llm_new_token(callbacks, content, msg_chunk, run_id)

                    if accumulated is None:
                        accumulated = msg_chunk
                    else:
                        accumulated = accumulated + msg_chunk

                    yield msg_chunk

                if callbacks and accumulated is not None:
                    full_reasoning = "".join(accumulated_reasoning)
                    final_additional_kwargs = dict(accumulated.additional_kwargs)
                    if full_reasoning:
                        final_additional_kwargs["reasoning_content"] = full_reasoning
                        final_additional_kwargs["thinking"] = full_reasoning
                    final_msg = AIMessage(
                        content=accumulated.content,
                        tool_calls=accumulated.tool_calls,
                        additional_kwargs=final_additional_kwargs,
                    )
                    await emit_llm_end(callbacks, final_msg, run_id)

                break

            except openai.APIError as e:
                if state.can_retry and self._is_retryable_error(e):
                    old_state = state
                    state = state.next_state()
                    logger.warning(f"⚠️ Context Error. Adapting: {old_state} -> {state}")
                    continue
                raise e

    def _is_retryable_error(self, e: Exception) -> bool:
        error_str = str(e).lower()
        retryable_keywords = ("context_length_exceeded", "maximum context length", "prompt is too long", "too many tokens")
        return any(kw in error_str for kw in retryable_keywords)

    async def ainvoke(self, messages: list[Any], config: dict = None, **kwargs: Any) -> Any:
        """Native non-streaming ainvoke wrapper that accumulates astream."""
        from app.core.engine.message.native_classes import AIMessage

        response_content = ""
        tool_calls = []
        additional_kwargs = {}
        reasoning_parts: list[str] = []

        async for chunk in self.astream(messages, config=config, **kwargs):
            if chunk.content:
                response_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
            if chunk.additional_kwargs:
                chunk_reasoning = chunk.additional_kwargs.get("reasoning_content") or ""
                if chunk_reasoning:
                    reasoning_parts.append(chunk_reasoning)
                else:
                    additional_kwargs.update(chunk.additional_kwargs)

        full_reasoning = "".join(reasoning_parts)
        if full_reasoning:
            additional_kwargs["reasoning_content"] = full_reasoning
            additional_kwargs["thinking"] = full_reasoning

        return AIMessage(
            content=response_content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs
        )

    async def summarize(self, text: str) -> str:
        """
        Generate a concise summary of the input text.
        """
        prompt_template = i18n.get("adaptive_llm.summarize_prompt")
        prompt = prompt_template.format(input=text)

        messages = [{"role": "user", "content": prompt}]
        response = ""
        async for chunk in self.astream(messages):
            response += chunk.content
        return response

    def with_structured_output(self, output_schema: type, method: str = "function_calling"):
        """
        Bind a Pydantic schema for structured output via function calling.
        Returns a wrapper whose ainvoke() yields a parsed instance of output_schema.
        """
        return _StructuredOutputWrapper(self, output_schema, method=method)


class _StructuredOutputWrapper:
    """Wrapper that enforces a structured Pydantic output via function calling."""

    def __init__(self, llm: "AdaptiveChatOpenAI", output_schema: type, method: str = "function_calling"):
        self._llm = llm
        self._schema = output_schema
        self._method = method

    def _build_tool_schema(self) -> dict:
        """Convert a Pydantic model class to an OpenAI function-tool schema."""
        schema = self._schema.model_json_schema()
        params = {
            "type": "object",
            "properties": schema.get("properties", {}),
        }
        if schema.get("required"):
            params["required"] = schema["required"]
        params.pop("title", None)
        params.pop("additionalProperties", None)
        if "$defs" in params:
            params.pop("$defs", None)
        return {
            "type": "function",
            "function": {
                "name": "submit_result",
                "description": self._schema.__doc__ or f"Submit a {self._schema.__name__} result.",
                "parameters": params,
            },
        }

    async def ainvoke(self, messages: list[Any], config: dict = None, **kwargs: Any) -> Any:
        """Call the LLM with the schema as a tool, then parse the tool-call args."""
        import json

        tool_schema = self._build_tool_schema()

        original_tools = self._llm._tools
        self._llm._tools = [tool_schema]
        try:
            response = await self._llm.ainvoke(messages, config=config, **kwargs)
        finally:
            self._llm._tools = original_tools

        tool_calls = response.tool_calls or []
        if not tool_calls:
            raise ValueError(
                f"Structured output: LLM returned no tool calls. "
                f"content={response.content[:200]}"
            )

        tc = tool_calls[0]
        raw_args = tc.get("args")
        if isinstance(raw_args, str):
            parsed_args = json.loads(raw_args) if raw_args.strip() else {}
        elif isinstance(raw_args, dict):
            parsed_args = raw_args
        else:
            parsed_args = {}

        return self._schema.model_validate(parsed_args)
