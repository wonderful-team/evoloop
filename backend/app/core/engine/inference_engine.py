"""
InferenceEngine - Pure LLM execution logic.

Responsible for:
- LLM initialization and provider detection
- Prompt caching optimizations
- ReAct loop and single-shot execution
- Telemetry recording
- LLM error classification

Explicitly NOT responsible for:
- Message hydration, repair, or windowing
- Signal interception (handled by SignalRegistry via interceptors)
- Blackboard parsing (handled by BlackboardParser)
"""

import hashlib
import logging
import time
from typing import Any, Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger  # noqa: E402


# Backward-compatible re-export
from app.core.engine.llm_error_classifier import InferenceError, classify_llm_error  # noqa: E402,F401


class InferenceEngine:
    """Instance-based inference engine for LLM ReAct loops."""

    def __init__(self, llm_factory: Any | None = None, context_trimmer: ContextTrimmer | None = None):
        self._llm_factory = llm_factory or LLMFactory
        self._context_trimmer = context_trimmer or ContextTrimmer()

    async def create_llm(self, model: str | None, temperature: float):
        """Initialize LLM and detect provider."""
        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature)
        provider = self._detect_provider(llm)
        return llm, provider

    def _detect_provider(self, llm) -> str:
        """Detect LLM provider for prompt-caching optimizations."""
        try:
            class_name = llm.__class__.__name__
            if "Anthropic" in class_name:
                return "anthropic"
            if hasattr(llm, "lc_secrets") and "anthropic" in str(llm.lc_secrets).lower():
                return "anthropic"
        except Exception:
            pass
        return "openai"

    def bind_tools(self, llm, tools: list[Any]):
        """Bind tools to LLM and return tool map."""
        if tools:
            return llm.bind_tools(tools), {t.name: t for t in tools}
        return llm, {}

    def build_system_messages(self, system_prompt: str, provider: str) -> list[SystemMessage]:
        """Build provider-optimized system messages."""
        if provider == "anthropic":
            return [SystemMessage(content=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }])]
        return [SystemMessage(content=system_prompt)]

    async def run_react_loop(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str,
        config: RunnableConfig,
        name: str,
        max_steps: int = 5,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
        on_thinking: Callable | None = None,
        model: str | None = None,
    ) -> dict:
        """
        Core ReAct loop.

        Args:
            interceptors: Mapping of tool_name -> async callable(tool_call, config).
                          If callable returns a non-None signal, the loop aborts and returns it.
            on_thinking: Optional callback(thinking_content) for parsed thinking blocks.

        Returns:
            dict with keys: messages, tool_history, last_response, is_truncated, signal
        """
        from app.core.monitoring.activity import activity_monitor

        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {"messages": [], "tool_history": [], "last_response": None, "is_truncated": False, "signal": None}

        new_messages = []
        local_tool_history = []
        last_response = None

        for i in range(max_steps):
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id:
                await activity_monitor.check_cancellation(thread_id)

            # Token-driven trim inside the ReAct loop.
            # loop_messages grows every turn; re-apply window+repair so the LLM
            # is never drowned by its own history.
            if model:
                trim_result = self._context_trimmer.trim(
                    messages=loop_messages,
                    model=model,
                    node_source=name.lower(),
                    stages={"window", "repair"},
                )
                if trim_result.trigger != TrimTrigger.NONE:
                    loop_messages = trim_result.messages
                    logger.info(
                        f"[{name}] ✂️ Loop trim: {trim_result.before_count} -> {trim_result.after_count} msgs, "
                        f"{trim_result.before_tokens} -> {trim_result.after_tokens} tokens"
                    )

            # Log context window size before each LLM call
            msg_count = len(loop_messages)
            from app.core.engine.message.utils import count_total_tokens
            token_count = count_total_tokens(loop_messages)
            logger.info(f"--- {name} Loop Step {i+1}/{max_steps} | Context: {msg_count} msgs, ~{token_count} tokens ---")

            try:
                start_perf = time.perf_counter()
                response = await llm_with_tools.ainvoke(loop_messages, config=config)
                latency = time.perf_counter() - start_perf

                from app.core.engine.telemetry_recorder import record_inference_telemetry
                record_inference_telemetry(
                    name=name, turn_id=i, system_prompt=system_prompt,
                    history_messages=history_messages, loop_messages=loop_messages,
                    response=response, latency=latency, metadata={"max_steps": max_steps}
                )
                last_response = response
            except Exception as e:
                from app.core.engine.llm_error_classifier import classify_llm_error
                raise classify_llm_error(e)

            # Inject run_id
            run_id = config.get("configurable", {}).get("run_id")
            if run_id:
                if not hasattr(response, "metadata"):
                    response.metadata = {}
                response.metadata["run_id"] = run_id
                if not hasattr(response, "additional_kwargs"):
                    response.additional_kwargs = {}
                response.additional_kwargs["run_id"] = run_id

            # Parse thinking content for logging / callback
            thinking_content = ""
            content_preview = str(response.content)[:200] if response.content else "(empty)"
            tool_calls_count = len(response.tool_calls) if hasattr(response, "tool_calls") and response.tool_calls else 0
            logger.info(f"[{name}] LLM response: content='{content_preview}...', tool_calls={tool_calls_count}")

            if response.content:
                thinking_content = response.content
            elif hasattr(response, "additional_kwargs") and "thought" in response.additional_kwargs:
                thinking_content = response.additional_kwargs["thought"]
                logger.info(f"[{name}] Thinking (from additional_kwargs): {thinking_content[:200]}...")

            if thinking_content and on_thinking:
                await on_thinking(thinking_content)
            if thinking_content:
                logger.info(f"[{name}] Thinking: {thinking_content}")

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            # Process tool calls
            pending_signal = None
            remaining_tool_calls = []

            for tc in response.tool_calls:
                if pending_signal is not None:
                    logger.warning(f"[{name}] Multiple signals detected in one turn. Ignoring additional: {tc['name']}")
                    continue

                interceptor = (interceptors or {}).get(tc["name"])
                if interceptor:
                    sig = await interceptor(tc, config)
                    if sig is not None:
                        pending_signal = sig
                        continue

                remaining_tool_calls.append(tc)

            if remaining_tool_calls and tool_executor is not None:
                tool_results = await tool_executor.execute_batch(
                    remaining_tool_calls, local_tool_history
                )
                for tool_msg in tool_results:
                    logger.info(f"[{name}] Result ({tool_msg.name}): {str(tool_msg.content)[:300]}...")
                    loop_messages.append(tool_msg)
                    new_messages.append(tool_msg)

            if pending_signal is not None:
                return {
                    "messages": new_messages,
                    "tool_history": local_tool_history,
                    "last_response": last_response,
                    "is_truncated": False,
                    "signal": pending_signal,
                }

        is_truncated = False
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] Hit max_steps ({max_steps}) with open tool calls.")
            truncation_msg = AIMessage(
                content=(
                    f"[TRUNCATION] Agent reached the maximum step limit ({max_steps}) "
                    f"with pending tool calls. The task may be incomplete or stuck in a loop. "
                    f"Supervisor review and replanning is required."
                ),
                metadata={"is_truncated": True, "max_steps": max_steps, "requires_replan": True}
            )
            new_messages.append(truncation_msg)
            is_truncated = True

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": last_response,
            "is_truncated": is_truncated,
            "signal": None,
        }

    async def run_single_shot(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str,
        config: RunnableConfig,
        name: str,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
    ) -> dict:
        """Single-shot execution for subtasks."""
        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {"messages": [], "tool_history": [], "last_response": None, "is_truncated": False}

        sys_hash = hashlib.md5(system_prompt.encode()).hexdigest()
        start_perf = time.perf_counter()
        try:
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
            latency = time.perf_counter() - start_perf

            logger.warning(f"[{name}] PROMPT CACHE DIAGNOSTIC: SystemPromptHash={sys_hash} | Latency={latency:.2f}s")

            self._record_telemetry(
                name=f"{name}_subtask", turn_id=0, system_prompt=system_prompt,
                history_messages=history_messages, loop_messages=loop_messages,
                response=response, latency=latency, metadata={"is_single_shot": True}
            )
        except Exception as e:
            from app.core.engine.llm_error_classifier import classify_llm_error
            raise classify_llm_error(e)

        # Inject run_id
        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            if not hasattr(response, "metadata"):
                response.metadata = {}
            response.metadata["run_id"] = run_id
            if not hasattr(response, "additional_kwargs"):
                response.additional_kwargs = {}
            response.additional_kwargs["run_id"] = run_id

        new_messages = [response]
        local_tool_history = []

        if tool_executor is not None and response.tool_calls:
            # Filter out tool calls that were intercepted (handled by SignalRegistry)
            intercepted_tools = set((interceptors or {}).keys())
            remaining = [tc for tc in response.tool_calls if tc["name"] not in intercepted_tools]
            if remaining:
                tool_results = await tool_executor.execute_batch(remaining, local_tool_history)
                for tool_msg in tool_results:
                    logger.info(f"[{name}] Result ({tool_msg.name}): {str(tool_msg.content)[:300]}...")
                    new_messages.append(tool_msg)

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": response,
            "is_truncated": False,
        }


