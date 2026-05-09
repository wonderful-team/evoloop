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

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.error_handler import with_llm_retry
from app.core.engine.error_handler import LLMErrorHandler
from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


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
        class_name = llm.__class__.__name__
        if "Anthropic" in class_name:
            return "anthropic"
        if "anthropic" in str(getattr(llm, "lc_secrets", {})).lower():
            return "anthropic"
        return "openai"

    def bind_tools(self, llm, tools: list[Any]):
        """Bind tools to LLM and return tool map."""
        if tools:
            return llm.bind_tools(tools), {t.name: t for t in tools}
        return llm, {}

    @staticmethod
    @with_llm_retry(max_attempts=3)
    async def _stream_llm_response(llm_with_tools, loop_messages, config):
        """Stream LLM response and accumulate chunks into a complete AIMessage.

        Uses astream() so on_llm_new_token callbacks fire for real-time
        thinking/streaming display. Falls back to ainvoke() on providers
        that don't support streaming (e.g. kimi with long context).
        """
        from langchain_core.messages import AIMessage, AIMessageChunk

        # astream() triggers on_llm_new_token callbacks for real-time thinking/streaming.
        # AdaptiveChatOpenAI handles retries and parameter reduction internally.
        response = None
        async for chunk in llm_with_tools.astream(loop_messages, config=config):
            if response is None:
                response = chunk
            else:
                response = response + chunk

        # Convert accumulated chunk to a proper AIMessage for downstream compatibility
        if isinstance(response, AIMessageChunk):
            response = AIMessage(
                content=response.content,
                additional_kwargs=response.additional_kwargs,
                tool_calls=response.tool_calls,
                response_metadata=response.response_metadata,
            )

        return response

    def build_system_messages(self, system_prompt: str, provider: str) -> list[SystemMessage]:
        """Build provider-optimized system messages."""
        if provider == "anthropic":
            return [SystemMessage(content=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }])]
        return [SystemMessage(content=system_prompt)]

    async def _prepare_turn_context(
        self,
        loop_messages: list[BaseMessage],
        model: str | None,
        name: str,
        thread_id: str | None,
        run_id: str | None,
        config: RunnableConfig
    ) -> list[BaseMessage]:
        """Trims context and logs context window size."""
        if model:
            trim_result = self._context_trimmer.trim(
                messages=loop_messages,
                model=model,
                node_source=name.lower(),  # type: ignore[arg-type]
                stages={"window", "repair"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                # Trigger PRE_COMPACT hook BEFORE applying the trim to save state
                from app.core.engine.hooks import HookContext, HookEvent, hook_system
                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=thread_id,
                        run_id=run_id,
                        messages=loop_messages,
                        project_id=config.get("configurable", {}).get("project_id"),
                        user_id=config.get("configurable", {}).get("user_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    )
                )

                loop_messages = trim_result.messages
                logger.info(
                    f"[{name}] ✂️ Loop trim: {trim_result.before_count} -> {trim_result.after_count} msgs, "
                    f"{trim_result.before_tokens} -> {trim_result.after_tokens} tokens"
                )

        # Log context window size before each LLM call
        msg_count = len(loop_messages)
        from app.core.engine.message.utils import count_total_tokens
        token_count = count_total_tokens(loop_messages)
        logger.info(f"--- {name} Context: {msg_count} msgs, ~{token_count} tokens ---")
        return loop_messages

    async def _execute_llm_call(
        self,
        llm_with_tools,
        loop_messages: list[BaseMessage],
        config: RunnableConfig,
        name: str,
        system_prompt: str,
        history_messages: list[BaseMessage],
        turn_id: int,
        on_thinking: Callable | None = None,
        max_steps: int | None = None,
        is_single_shot: bool = False,
        sys_hash: str | None = None,
    ) -> AIMessage:
        """Executes LLM call and extracts reasoning."""
        try:
            start_perf = time.perf_counter()
            response = await self._stream_llm_response(llm_with_tools, loop_messages, config)
            latency = time.perf_counter() - start_perf

            if is_single_shot and sys_hash:
                logger.warning(f"[{name}] PROMPT CACHE DIAGNOSTIC: SystemPromptHash={sys_hash} | Latency={latency:.2f}s")

            # [DIAGNOSTIC] Deep inspection of raw response
            logger.debug(
                f"[{name}] 🔍 RAW RESPONSE DIAGNOSTIC:\n"
                f"  - Content length: {len(response.content)}\n"
                f"  - Tool Calls: {response.tool_calls}\n"
                f"  - Invalid Tool Calls: {response.invalid_tool_calls}\n"
                f"  - Additional Kwargs: {list(response.additional_kwargs.keys())}\n"
                f"  - Finish Reason: {response.response_metadata.get('finish_reason')}\n"
                f"  - Model Metadata: {response.response_metadata}\n"
            )

        except Exception as e:
            LLMErrorHandler.raise_inference_error(e)

        # Inject run_id
        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            response.additional_kwargs["run_id"] = run_id

        # Extract thinking content using unified utility
        thinking_content = extract_reasoning_from_message(response)
        if thinking_content:
            logger.info(f"[{name}] Thinking: {thinking_content[:200]}...")
            if on_thinking:
                await on_thinking(thinking_content)

        return response

    async def _process_tool_executions(
        self,
        response: AIMessage,
        name: str,
        config: RunnableConfig,
        interceptors: dict[str, Callable] | None,
        tool_executor: Any | None,
        local_tool_history: list
    ) -> tuple[list[BaseMessage], Any | None]:
        """Processes tool calls, handles interceptors, and executes tools."""
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

        tool_results = []
        if remaining_tool_calls and tool_executor is not None:
            logger.info(f"[{name}] 🛠️ Executing {len(remaining_tool_calls)} tool calls via tool_executor")
            res, batch_signal = await tool_executor.execute_batch(remaining_tool_calls, local_tool_history)
            tool_results = res
            
            if batch_signal and pending_signal is None:
                logger.info(f"[{name}] ⚡ Post-execution signal detected: {type(batch_signal).__name__}")
                pending_signal = batch_signal

            logger.info(f"[{name}] 📦 tool_results returned: {len(tool_results)} items")
            for tool_msg in tool_results:
                logger.info(f"[{name}] Result ({tool_msg.name}): {str(tool_msg.content)[:200]}...")
        else:
            if remaining_tool_calls:
                logger.warning(f"[{name}] ⚠️ tool_executor is None! Cannot execute {len(remaining_tool_calls)} tool calls.")
            else:
                logger.info(f"[{name}] ℹ️ No remaining tool_calls after interception.")

        return tool_results, pending_signal

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

        Returns:
            dict with keys: messages, tool_history, last_response, is_truncated, signal
        """
        from app.core.monitoring.activity import activity_monitor

        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        loop_messages: list[BaseMessage] = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {"messages": [], "tool_history": [], "last_response": None, "is_truncated": False, "signal": None}

        new_messages: list[BaseMessage] = []
        local_tool_history = []
        last_response = None

        logger.info(f"[{name}] ▶️ run_react_loop START | model={model} | max_steps={max_steps} | msg_count={len(messages)} | tool_executor={'YES' if tool_executor else 'NO'}")

        for i in range(max_steps):
            thread_id = config.get("configurable", {}).get("thread_id")
            run_id = config.get("configurable", {}).get("run_id")
            if thread_id:
                await activity_monitor.check_cancellation(thread_id)

            loop_messages = await self._prepare_turn_context(
                loop_messages=loop_messages,
                model=model,
                name=name,
                thread_id=thread_id,
                run_id=run_id,
                config=config,
            )

            response = await self._execute_llm_call(
                llm_with_tools=llm_with_tools,
                loop_messages=loop_messages,
                config=config,
                name=name,
                system_prompt=system_prompt,
                history_messages=history_messages,
                turn_id=i,
                on_thinking=on_thinking,
                max_steps=max_steps,
            )
            last_response = response

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            logger.info(f"[{name}] 🔧 tool_calls detected: {len(response.tool_calls)} calls")

            tool_results, pending_signal = await self._process_tool_executions(
                response=response,
                name=name,
                config=config,
                interceptors=interceptors,
                tool_executor=tool_executor,
                local_tool_history=local_tool_history
            )

            for tool_msg in tool_results:
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
                additional_kwargs={"is_truncated": True, "max_steps": max_steps, "requires_replan": True}
            )
            new_messages.append(truncation_msg)
            is_truncated = True

        logger.info(
            f"[{name}] ⏹️ run_react_loop END | new_messages={len(new_messages)} | "
            f"types={[type(m).__name__ for m in new_messages]} | "
            f"truncated={is_truncated}"
        )
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

        response = await self._execute_llm_call(
            llm_with_tools=llm_with_tools,
            loop_messages=loop_messages,
            config=config,
            name=name,
            system_prompt=system_prompt,
            history_messages=history_messages,
            turn_id=0,
            is_single_shot=True,
            sys_hash=sys_hash,
        )

        new_messages: list[BaseMessage] = [response]
        local_tool_history = []

        if response.tool_calls:
            tool_results, batch_signal = await self._process_tool_executions(
                response=response,
                name=name,
                config=config,
                interceptors=interceptors,
                tool_executor=tool_executor,
                local_tool_history=local_tool_history
            )
            
            for tool_msg in tool_results:
                new_messages.append(tool_msg)
        else:
            batch_signal = None

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": response,
            "is_truncated": False,
            "signal": batch_signal,
        }
