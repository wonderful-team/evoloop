import copy
import inspect
import json
import logging
import typing
from collections.abc import AsyncGenerator
from typing import Any

import openai
from pydantic import BaseModel, create_model

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


def _to_openai_tool_call(tc: dict) -> dict:
    """Normalize a native tool-call dict to the standard OpenAI wire format.

    Native shape (used across the engine): ``{"index", "id", "name", "args"}``.
    The EvoLoop gateway's OpenAI→anthropic translation requires the standard
    function-wrapped shape; passing the native shape through verbatim makes
    some upstream endpoints answer 400 on any
    multi-step tool loop.
    """
    if "function" in tc:
        return tc
    tc_id = tc.get("id") or ""
    tc_name = tc.get("name") or ""
    args = tc.get("args")
    if isinstance(args, (dict, list)):
        args = json.dumps(args, ensure_ascii=False)
    if not tc_id and not tc_name:
        return None
    return {
        "id": tc_id,
        "type": "function",
        "function": {
            "name": tc_name,
            "arguments": args or "",
        },
    }


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
            current_temperature=max(self.current_temperature - 0.2, 0.0),
        )

    @property
    def can_retry(self) -> bool:
        return self.attempt < self.max_retries


class AdaptiveChatOpenAI:
    """
    A robust, native, SDK-free ChatOpenAI wrapper that implements DeepCode's 'Adaptive Token Strategy'.
    """

    provider = "openai"
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
        **kwargs: Any,
    ):
        self.model = model
        self.temperature = temperature
        self.streaming = streaming
        self.max_tokens = max_tokens
        self.extra_body = extra_body or {}
        self.default_headers = default_headers or {}
        self._tools = []
        self._tool_choice: str | None = None

        # Create native async OpenAI client
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_async_client,
            default_headers=default_headers,
        )

    def bind_tools(self, tools: list[Any], tool_choice: str | None = None) -> "AdaptiveChatOpenAI":
        # Operate on a copy, not self: LLMFactory caches LLM instances per
        # config, so mutating self would leak tools/tool_choice into later
        # raw calls that reuse the cached instance (observed: the voice
        # router's tool_choice="required" binding poisoned decompose's raw
        # calls, which then returned tool-call responses with empty content).
        bound = copy.copy(self)
        bound._tools = []
        bound._tool_choice = tool_choice
        for t in tools:
            # Accept pre-built OpenAI function schemas (dicts) verbatim — used by
            # the voice router which hands us ROUTE_TOOLS already in wire format.
            if isinstance(t, dict):
                if t.get("type") == "function" and "function" in t:
                    bound._tools.append(t)
                continue
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
            bound._tools.append(t_schema)
        return bound

    async def astream(self, messages: list[Any], config: dict = None, **kwargs: Any) -> AsyncGenerator[AIMessageChunk, None]:
        from app.core.engine.callbacks.bridge import (
            _get_callbacks,
            _get_metadata,
            _get_run_id,
            emit_llm_end,
            emit_llm_new_token,
            emit_llm_start,
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
                # model_dump() from BaseMessage subclasses includes "type" but not "role"
                if "role" not in m:
                    role_map = {
                        "ai": "assistant",
                        "human": "user",
                        "system": "system",
                        "tool": "tool",
                    }
                    m = {**m, "role": role_map.get(m.get("type", ""), "user")}
                # Extract reasoning_content from additional_kwargs/thinking.
                # Only add the field when real reasoning content exists; do not
                # fabricate a placeholder so reasoning-model providers can accept
                # messages that did not emit reasoning tokens.
                if m.get("role") == "assistant":
                    akw = m.get("additional_kwargs") or {}
                    rc = akw.get("reasoning_content") or akw.get("thinking")
                    if rc:
                        m = {**m, "reasoning_content": rc}
                    # Dict messages may carry native tool_calls; normalize them
                    # to the OpenAI wire format before sending upstream.
                    if m.get("tool_calls"):
                        calls = [_to_openai_tool_call(tc) for tc in m["tool_calls"]]
                        m = {**m, "tool_calls": [c for c in calls if c is not None]}
                api_messages.append(m)
            else:
                role = (
                    "assistant"
                    if m.type == "ai"
                    else (m.type if m.type in ("system", "tool") else "user")
                )
                msg_dict = {"role": role, "content": m.content}
                if role == "tool" and m.tool_call_id:
                    msg_dict["tool_call_id"] = m.tool_call_id
                elif role == "assistant":
                    if m.tool_calls:
                        calls = [_to_openai_tool_call(tc) for tc in m.tool_calls]
                        msg_dict["tool_calls"] = [c for c in calls if c is not None]
                    rc = (m.additional_kwargs or {}).get("reasoning_content") or (
                        m.additional_kwargs or {}
                    ).get("thinking")
                    if rc:
                        msg_dict["reasoning_content"] = rc
                api_messages.append(msg_dict)

        if callbacks:
            await emit_llm_start(callbacks, run_id, metadata)

        reasoning_degraded = False

        while True:
            try:
                req_params = {
                    "messages": api_messages,
                    "temperature": state.current_temperature,
                    "stream": True,
                    "extra_body": self.extra_body,
                    # 要求网关/上游在流式末尾返回 usage，用于计费与缓存命中分析
                    "stream_options": {"include_usage": True},
                }
                # Always pass model key to satisfy openai SDK (can be empty string for cloud default routing)
                req_params["model"] = self.model or ""
                if state.current_max_tokens:
                    req_params["max_tokens"] = state.current_max_tokens
                if self._tools:
                    req_params["tools"] = self._tools
                    if self._tool_choice is not None:
                        req_params["tool_choice"] = self._tool_choice

                if state.attempt > 0:
                    logger.info(f"🔄 Adaptive Retry {state.attempt}/{state.max_retries}: {state}")

                # Debugging logging: print all roles, content snippet, and reasoning_content presence
                for idx, msg in enumerate(api_messages):
                    role = msg.get("role")
                    content = msg.get("content") or ""
                    has_rc = "reasoning_content" in msg
                    rc_val = msg.get("reasoning_content")
                    logger.info(f"  Msg #{idx} | Role: {role} | Content: {content[:80]}... | HasRC: {has_rc} | RC: {str(rc_val)[:40]}...")

                stream = await self.client.chat.completions.create(**req_params)

                accumulated: AIMessageChunk | None = None
                accumulated_reasoning: list[str] = []
                usage = None
                async for chunk in stream:
                    if chunk.usage is not None:
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    content = (
                        (getattr(delta, "content", None) or "")
                        .replace("</s>", "")
                        .replace("<|im_end|>", "")
                        .replace("<|endoftext|>", "")
                    )
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
                        additional_kwargs=additional_kwargs,
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

                if usage is not None:
                    u = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
                    details = u.get("prompt_tokens_details") or {}
                    cached = details.get("cached_tokens") if isinstance(details, dict) else None
                    logger.info(
                        "[LLMUsage] model=%s input=%s output=%s cache_hit=%s cache_miss=%s cache_read=%s cache_creation=%s cached_tokens=%s",
                        self.model,
                        u.get("prompt_tokens"),
                        u.get("completion_tokens"),
                        u.get("prompt_cache_hit_tokens"),
                        u.get("prompt_cache_miss_tokens"),
                        u.get("cache_read_tokens"),
                        u.get("cache_creation_tokens"),
                        cached,
                    )

                break

            except openai.APIError as e:
                error_str = str(e).lower()
                if "reasoning_content" in error_str and not reasoning_degraded:
                    # Only strip reasoning_content from the retry if the provider explicitly
                    # says it is not allowed.
                    disallow_reasoning_keywords = (
                        "is not allowed",
                        "not permitted",
                        "not supported",
                        "cannot be used",
                        "cannot pass",
                        "is not valid",
                        "reasoning model is not supported",
                        "unsupported",
                    )
                    if any(kw in error_str for kw in disallow_reasoning_keywords):
                        reasoning_degraded = True
                        for msg in api_messages:
                            msg.pop("reasoning_content", None)
                        logger.warning("⚠️ Reasoning Content Error. Stripping and retrying.")
                        continue
                    # A reasoning_content error that is NOT an "not allowed" rejection
                    # cannot be fixed by retrying identical messages — stripping is
                    # disallowed and the payload is unchanged, so the next attempt
                    # fails identically. Surface the error directly instead of
                    # burning a guaranteed-fail retry.
                    logger.warning(
                        "⚠️ Reasoning Content Error not resolvable by retry: %s",
                        error_str[:200],
                    )
                    raise e
                if state.can_retry and self._is_retryable_error(e):
                    old_state = state
                    state = state.next_state()
                    logger.warning(f"⚠️ Context Error. Adapting: {old_state} -> {state}")
                    continue
                raise e

    def _is_retryable_error(self, e: Exception) -> bool:
        error_str = str(e).lower()
        retryable_keywords = (
            "context_length_exceeded",
            "maximum context length",
            "prompt is too long",
            "too many tokens",
        )
        return any(kw in error_str for kw in retryable_keywords)

    async def ainvoke(self, messages: list[Any], config: dict = None, **kwargs: Any) -> Any:
        """Native non-streaming ainvoke wrapper that accumulates astream."""
        from app.core.engine.message.native_classes import AIMessage

        response_content = ""
        tool_call_slots: dict[int, dict] = {}
        additional_kwargs = {}
        reasoning_parts: list[str] = []

        async for chunk in self.astream(messages, config=config, **kwargs):
            if chunk.content:
                response_content += chunk.content
            if chunk.tool_calls:
                # Streaming tool-calls arrive as deltas: the first chunk carries
                # the name/id with an empty args string, and subsequent chunks
                # carry only args fragments (name/id=None). They MUST be merged
                # by index back into a single tool-call with the full JSON args;
                # treating each delta as a standalone call yields an empty args
                # on slot 0 and silently corrupts every downstream consumer
                # (voice router, structured output, ...).
                for tc in chunk.tool_calls:
                    idx = tc.get("index") or 0
                    slot = tool_call_slots.setdefault(idx, {"index": idx, "id": None, "name": None, "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    if tc.get("name"):
                        slot["name"] = tc["name"]
                    if tc.get("args"):
                        slot["args"] += tc["args"]
            if chunk.additional_kwargs:
                chunk_reasoning = chunk.additional_kwargs.get("reasoning_content") or ""
                if chunk_reasoning:
                    reasoning_parts.append(chunk_reasoning)
                else:
                    additional_kwargs.update(chunk.additional_kwargs)

        tool_calls = [tool_call_slots[i] for i in sorted(tool_call_slots)]

        full_reasoning = "".join(reasoning_parts)
        if full_reasoning:
            additional_kwargs["reasoning_content"] = full_reasoning
            additional_kwargs["thinking"] = full_reasoning

        return AIMessage(
            content=response_content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs,
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


def _inline_json_schema_refs(schema: dict) -> dict:
    """Resolve ``#/$defs/*`` references inline and drop ``$defs``.

    Pydantic v2 emits nested models as ``$ref`` + ``$defs``; some providers
    do not resolve ``$defs`` and return 400 ("$defs not found
    for reference"). Inline every reference so the schema is self-contained.
    Cyclic references degrade to ``{}`` to avoid infinite recursion.
    """
    defs = schema.get("$defs", {}) or {}

    def resolve(node, seen):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref[len("#/$defs/") :]
                if name in seen:
                    return {}
                target = defs.get(name)
                if isinstance(target, dict):
                    merged = {k: v for k, v in node.items() if k != "$ref"}
                    merged.update(resolve(target, seen | {name}))
                    return resolve(merged, seen | {name})
            return {k: resolve(v, seen) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x, seen) for x in node]
        return node

    out = resolve(schema, frozenset())
    if isinstance(out, dict):
        out.pop("$defs", None)
    return out


class _StructuredOutputWrapper:
    """Wrapper that enforces a structured Pydantic output via function calling."""

    def __init__(self, llm: "AdaptiveChatOpenAI", output_schema: type, method: str = "function_calling"):
        self._llm = llm
        self._schema = output_schema
        self._method = method

    def _build_tool_schema(self) -> dict:
        """Convert a Pydantic model class to an OpenAI function-tool schema."""
        schema = _inline_json_schema_refs(self._schema.model_json_schema())
        params = {
            "type": "object",
            "properties": schema.get("properties", {}),
        }
        if schema.get("required"):
            params["required"] = schema["required"]
        params.pop("title", None)
        params.pop("additionalProperties", None)
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
