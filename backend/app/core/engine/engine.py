"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.

This module provides the main AgentEngine class as an instance-based
alternative to the static methods. Supports dependency injection for
easier testing and extensibility.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from pydantic import Field

from app.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_WINDOW_SIZE,
    NODE_WINDOW_SIZES,
)
from app.core.engine.message_utils import (
    apply_forgotten_status,
    repair_message_history,
    smart_window_slice,
)
from app.core.engine.signals import AgentSignal
from app.core.engine.state import AgentState, BlackboardState, BlackboardMetadata, ensure_state, RunnableConfigMetadata
from app.core.engine.state.history import ToolCall
from app.core.engine.tools import AgentToolExecutor, ToolExecutionResult
from app.core.memory.tool_output_memory import get_tool_memory_from_state
from app.core.engine.signals import signal_manager
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.telemetry import agent_telemetry
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class EngineResult(DynamicBaseModel):
    """Structured result from AgentEngine.run_node() and internal execution methods."""
    messages: list[Any] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)
    blackboard: BlackboardState | None = None
    is_truncated: bool = False
    signal: AgentSignal | None = None
    routing_target: str | None = None


class AgentEngine:
    """
    Instance-based execution engine for EvoLoop Agents.

    Supports dependency injection for easier testing and extensibility.

    Example:
        # Using default dependencies
        engine = AgentEngine()
        result = await engine.run_node(state, config, system_prompt, tools)

        # With custom dependencies (for testing)
        engine = AgentEngine(
            llm_factory=mock_llm_factory,
            config_service=mock_config_service,
        )
    """

    def __init__(
        self,
        llm_factory: Any | None = None,
        config_service: Any | None = None,
        tool_executor_class: type = AgentToolExecutor,
        enable_diff_tracking: bool = True,
    ):
        """
        Initialize AgentEngine with optional dependency injection.

        Args:
            llm_factory: Optional LLM factory (defaults to LLMFactory)
            config_service: Optional config service (defaults to SystemConfigService)
            tool_executor_class: Tool executor class (defaults to AgentToolExecutor)
            enable_diff_tracking: Whether to enable diff tracking for file operations
        """
        self._llm_factory = llm_factory or LLMFactory
        self._config_service = config_service or SystemConfigService
        self._tool_executor_class = tool_executor_class
        self._enable_diff_tracking = enable_diff_tracking

    @staticmethod
    def _normalize_tool_calls(raw_tool_calls: list[dict[str, Any]] | None) -> list[ToolCall]:
        """Convert LangChain raw tool call dicts into structured ToolCall models."""
        if not raw_tool_calls:
            return []
        normalized = []
        for tc in raw_tool_calls:
            if isinstance(tc, ToolCall):
                normalized.append(tc)
            else:
                normalized.append(
                    ToolCall(
                        id=tc.get("id", gen_uuid()),
                        name=tc.get("name", ""),
                        args=tc.get("args", {}),
                    )
                )
        return normalized

    async def run_node(
        self,
        state: AgentState,
        config: RunnableConfig,
        system_prompt: str,
        tools: list[Any],
        model: str = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        name: str = "Agent",
        is_subtask: bool = False,
        node_source: str = None,
        parallel_tools: bool = False,
    ) -> EngineResult:
        """
        Executes the standard Agent ReAct loop.

        Args:
            is_subtask: If True, uses single-shot execution (no ReAct loop).
                       Subtasks must execute tools immediately in one turn.
        """
        # 1. Initialize LLM (with instance caching for performance)
        config_meta = RunnableConfigMetadata.from_config(config)
        if model is None:
            model = config_meta.model

        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature)

        # 1.1 Detect Provider for Prompt Caching
        provider = "openai"
        try:
            # Check class name or specific adapter types
            class_name = llm.__class__.__name__
            if "Anthropic" in class_name:
                provider = "anthropic"
            elif hasattr(llm, "lc_secrets") and "anthropic" in str(llm.lc_secrets).lower():
                provider = "anthropic"
        except Exception:
            pass

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Config & Context
        config = self._setup_callbacks(config)

        # 2.1 Unified Hydration (Phase 1 Optimization)
        from app.core.engine.state import ensure_state
        from app.core.engine.context_hydrator import EvoContextMiddleware
        state = await EvoContextMiddleware.hydrate(state, config)
        state = ensure_state(state)
        logger.info(f"[{name}] 🧪 Context Hydrated via Middleware")

        # 3. Message Handling & Repair
        raw_messages = list(list(state.messages))
        logger.info(f"[{name}] 📨 Raw messages: {len(raw_messages)} | Types: {[type(m).__name__ for m in raw_messages]}")

        # 3.0 Context Pruning removed - Agent-controlled forgetting replaces it

        # 3.1 Apply Agent-Controlled Forgetting
        tool_memory = get_tool_memory_from_state(state)
        messages_with_forgetting = apply_forgotten_status(raw_messages, tool_memory)
        logger.info(f"[{name}] 🧠 After forgetting: {len(messages_with_forgetting)} messages")

        # 3.2 Hierarchical Smart Windowing
        effective_window = NODE_WINDOW_SIZES.get(node_source, DEFAULT_WINDOW_SIZE)
        windowed_messages = await smart_window_slice(
            messages_with_forgetting,
            window_size=effective_window,
            max_total_chars=DEFAULT_CONTEXT_LIMIT,
            model=model,
            node_source=node_source or "default",
            thread_id=config_meta.thread_id,
            user_id=config_meta.user_id,
            project_id=config_meta.project_id,
        )

        logger.info(
            f"[{name}] 📐 Window: {len(messages_with_forgetting)} -> {len(windowed_messages)} messages "
            f"(forgotten: {len(tool_memory.forgotten)}, node={node_source}, window={effective_window})"
        )

        # 3.2 Repair Orphaned Tool Messages
        repaired_messages = repair_message_history(windowed_messages)
        logger.info(f"[{name}] 🔧 After repair: {len(repaired_messages)} messages | Types: {[type(m).__name__ for m in repaired_messages]}")

        # 4. Execution Mode Selection
        if is_subtask:
            logger.info(f"[{name}] 🎯 Single-shot mode (subtask) - executing immediately")
            result = await self._execute_single_shot(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                provider=provider, # Pass detected provider
                config=config,
                config_meta=config_meta,
                name=name,
                state=state,
                parallel_tools=parallel_tools,
            )
        else:
            result = await self._execute_react_loop(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                provider=provider, # Pass detected provider
                config=config,
                config_meta=config_meta,
                max_steps=max_steps,
                name=name,
                state=state,
                parallel_tools=parallel_tools,
            )

        # Add node_source marker to AI messages
        if node_source:
            for msg in result.messages or []:
                if isinstance(msg, AIMessage) and msg.content:
                    if not hasattr(msg, "metadata"):
                        msg.metadata = {}
                    if msg.metadata is None:
                        msg.metadata = {}
                    msg.metadata["node_source"] = node_source

        return result

    def _setup_callbacks(self, config: RunnableConfig) -> RunnableConfig:
        """Inject TraceCallbackHandler for Imitation/Reinforcement Learning."""
        return config

    async def _execute_react_loop(
        self,
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str, # Added provider
        config: RunnableConfig,
        config_meta: RunnableConfigMetadata,
        name: str,
        state: AgentState,
        max_steps: int = 10,
        parallel_tools: bool = True,
    ) -> EngineResult:
        """Core ReAct Loop Logic."""
        state = ensure_state(state)
        # 0. Build optimized system messages for Prompt Caching
        system_messages = self._build_system_messages(system_prompt, messages, provider)

        # 1. Separate context ticket and history messages
        # Standard ReAct: System + History
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] 🔴 No history messages! Returning empty.")
            return EngineResult(messages=[])

        new_messages = []
        local_tool_history = []
        last_response = None

        for i in range(max_steps):
            # Check for cancellation
            if config_meta.thread_id:
                await activity_monitor.check_cancellation(config_meta.thread_id)

            logger.info(f"--- {name} Loop Step {i+1} ---")

            # Invoke LLM
            try:
                start_perf = time.perf_counter()
                response = await llm_with_tools.ainvoke(loop_messages, config=config)
                latency = time.perf_counter() - start_perf

                # [TELEMETRY] Record inference
                agent_telemetry.record_inference(
                    node_name=name,
                    turn_id=i,
                    prompt_info={
                        "system_len": len(system_prompt),
                        "history_len": sum(len(str(m.content)) for m in history_messages),
                        "total_len": len(system_prompt) + sum(len(str(m.content)) for m in loop_messages)
                    },
                    response_info={
                        "content": response.content,
                        "usage": getattr(response, "usage_metadata", {}),
                        "is_tool_call": bool(response.tool_calls),
                        "tool_names": [tc.name for tc in self._normalize_tool_calls(response.tool_calls)]
                    },
                    latency_ms=latency * 1000,
                    metadata={"max_steps": max_steps, "parallel_tools": parallel_tools}
                )

                last_response = response
            except Exception as e:
                return self._handle_llm_exception(e, name, state)

            # Inject run_id
            if config_meta.run_id:
                if not hasattr(response, "metadata"):
                    response.metadata = {}
                response.metadata["run_id"] = config_meta.run_id
                if not hasattr(response, "additional_kwargs"):
                    response.additional_kwargs = {}
                response.additional_kwargs["run_id"] = config_meta.run_id

            # Parse thinking content
            thinking_content = ""
            content_preview = str(response.content)[:200] if response.content else "(empty)"
            tool_calls_count = len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0
            logger.info(f"[{name}] 📥 LLM response: content='{content_preview}...', tool_calls={tool_calls_count}")

            if response.content:
                thinking_content = response.content
            elif hasattr(response, "additional_kwargs") and "thought" in response.additional_kwargs:
                thinking_content = response.additional_kwargs["thought"]
                logger.info(f"[{name}] 🧠 Thinking (from additional_kwargs): {thinking_content[:200]}...")

            if thinking_content:
                logger.info(f"[{name}] 🧠 Thinking: {thinking_content}")
                state.blackboard = self._parse_inferred_blackboard(
                    thinking_content, state.blackboard, name
                )

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] 🏁 Finished with text response (no tool calls).")
                break

            from app.core.callbacks.transparent import TransparentCallbackHandler
            from app.core.tools.executor import ToolExecutor as _ToolExecutor

            # Turn-level signal tracking
            pending_signal = None

            # Extract TransparentCallbackHandler to restore observability for intercepted tools
            evoloop_handler = None
            callbacks = config.get("callbacks", []) if config else []
            callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
            for cb in callback_list:
                if isinstance(cb, TransparentCallbackHandler):
                    evoloop_handler = cb
                    break

            tool_calls = self._normalize_tool_calls(response.tool_calls)

            # 1. Intercept Pre-Execution Signals (e.g., route_to)
            signal_tools = []
            for tc in tool_calls:
                signal = await signal_manager.intercept(tc)
                if signal:
                    # Observability for virtual tools
                    if evoloop_handler:
                        try:
                            await evoloop_handler.on_tool_start(
                                serialized={"name": tc.name},
                                input_str=json.dumps(tc.args, ensure_ascii=False),
                                run_id=tc.id
                            )
                        except Exception as e:
                            logger.error(f"Failed to log intercepted tool start: {e}")

                    pending_signal = signal
                    output_msg = f"Signal emitted: {tc.name}"
                    
                    # Protocol fulfillment: every tool_call gets a response
                    new_messages.append(ToolMessage(
                        content=output_msg,
                        tool_call_id=tc.id,
                        name=tc.name,
                        id=gen_uuid(),
                    ))

                    if evoloop_handler:
                        try:
                            await evoloop_handler.on_tool_end(output=output_msg, run_id=tc.id)
                        except Exception as e:
                            logger.error(f"Failed to log intercepted tool end: {e}")

                    signal_tools.append(tc.name)
                    break # Single signal per turn priority

            # 2. Execute Non-Intercepted Tools
            remaining_tool_calls = [tc for tc in tool_calls if tc.name not in signal_tools]

            if remaining_tool_calls:
                tool_executor = self._tool_executor_class(
                    tool_map=tool_map,
                    state=state,
                    config=config,
                    name=name,
                    enable_diff_tracking=self._enable_diff_tracking,
                )

                async def _process_single_tool(tc: ToolCall) -> "ToolExecutionResult":
                    return await tool_executor.execute_tool(
                        tool_name=tc.name,
                        tool_args=tc.args,
                        tool_id=tc.id,
                        local_tool_history=local_tool_history,
                    )

                if parallel_tools:
                    logger.info(f"[{name}] ⚡ Executing {len(remaining_tool_calls)} tools in parallel")
                    tool_results = await asyncio.gather(*[_process_single_tool(tc) for tc in remaining_tool_calls])
                else:
                    logger.info(f"[{name}] ⛓️ Executing {len(remaining_tool_calls)} tools sequentially")
                    tool_results = []
                    for tc in remaining_tool_calls:
                        res = await _process_single_tool(tc)
                        tool_results.append(res)

                for res in tool_results:
                    tool_msg = res.message
                    raw_content = res.raw_result
                    
                    logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:300])}...")
                    loop_messages.append(tool_msg)
                    new_messages.append(tool_msg)

                    # 3.1 Check for Post-Execution Signals (Standardized)
                    if not pending_signal:
                        signal = signal_manager.detect_post_execution_signal(tool_msg.name, raw_content)
                        if signal:
                            pending_signal = signal
                            # We found a signal, but we continue processing other parallel results 
                            # if they were already gathering. However, we won't detect more signals.

            # 4. Dispatch Signal if present after tool execution
            if pending_signal:
                return EngineResult(
                    messages=new_messages,
                    signal=pending_signal,
                    tool_history=local_tool_history,
                    blackboard=state.blackboard,
                )

        # Loop ended
        is_truncated = False
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] 🔴 Hit max_steps ({max_steps}) with open tool calls.")
            truncation_msg = AIMessage(
                content="Execution reached maximum step limit and was paused.",
                metadata={"is_truncated": True, "max_steps": max_steps}
            )
            new_messages.append(truncation_msg)
            is_truncated = True

        return EngineResult(
            messages=new_messages,
            tool_history=local_tool_history,
            blackboard=state.blackboard,
            is_truncated=is_truncated,
        )

    async def _execute_single_shot(
        self,
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str, # Added provider
        config: RunnableConfig,
        config_meta: RunnableConfigMetadata,
        name: str,
        state: AgentState,
        parallel_tools: bool = False,
    ) -> EngineResult:
        """Single-shot execution for subtasks."""
        state = ensure_state(state)
        # Build optimized system messages for Prompt Caching
        system_messages = self._build_system_messages(system_prompt, messages, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] 🔴 No history messages! Returning empty.")
            return EngineResult(messages=[])

        # [DIAGNOSTIC] Capture System Prompt stability and Latency
        sys_hash = hashlib.md5(system_prompt.encode()).hexdigest()
        start_perf = time.perf_counter()
        try:
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
            latency = time.perf_counter() - start_perf

            logger.warning(f"[{name}] 🧩 PROMPT CACHE DIAGNOSTIC: SystemPromptHash={sys_hash} | Latency={latency:.2f}s")

            # [TELEMETRY] Record inference
            agent_telemetry.record_inference(
                node_name=f"{name}_subtask",
                turn_id=0,
                prompt_info={
                    "system_len": len(system_prompt),
                    "history_len": sum(len(str(m.content)) for m in history_messages),
                    "total_len": len(system_prompt) + sum(len(str(m.content)) for m in loop_messages)
                },
                response_info={
                    "content": response.content,
                    "usage": getattr(response, "usage_metadata", {}),
                    "is_tool_call": bool(response.tool_calls),
                    "tool_names": [tc.name for tc in self._normalize_tool_calls(response.tool_calls)]
                },
                latency_ms=latency * 1000,
                metadata={"is_single_shot": True}
            )
        except Exception as e:
            return self._handle_llm_exception(e, name, state)

        # Inject run_id
        if config_meta.run_id:
            if not hasattr(response, "metadata"):
                response.metadata = {}
            response.metadata["run_id"] = config_meta.run_id
            if not hasattr(response, "additional_kwargs"):
                response.additional_kwargs = {}
            response.additional_kwargs["run_id"] = config_meta.run_id

        new_messages = [response]
        local_tool_history = []

        # Parse blackboard
        state.blackboard = self._parse_inferred_blackboard(
            response.content, state.blackboard, name
        )

        tool_calls = self._normalize_tool_calls(response.tool_calls)

        # 1. Intercept Pre-Execution Signals
        signal_tools = []
        pending_signal = None
        
        # Pull evoloop_handler for signal observability
        evoloop_handler = None
        callbacks = config.get("callbacks", []) if config else []
        callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
        from app.core.callbacks.transparent import TransparentCallbackHandler
        for cb in callback_list:
            if isinstance(cb, TransparentCallbackHandler):
                evoloop_handler = cb
                break
        
        for tc in tool_calls:
            signal = await signal_manager.intercept(tc)
            if signal:
                if evoloop_handler:
                    try:
                        await evoloop_handler.on_tool_start(
                            serialized={"name": tc.name},
                            input_str=json.dumps(tc.args, ensure_ascii=False),
                            run_id=tc.id
                        )
                    except Exception as e:
                        logger.error(f"Failed to log intercepted tool start: {e}")

                pending_signal = signal
                output_msg = f"Signal emitted: {tc.name}"
                new_messages.append(ToolMessage(
                    content=output_msg,
                    tool_call_id=tc.id,
                    name=tc.name,
                    id=gen_uuid(),
                ))
                
                if evoloop_handler:
                    try:
                        await evoloop_handler.on_tool_end(output=output_msg, run_id=tc.id)
                    except Exception as e:
                        logger.error(f"Failed to log intercepted tool end: {e}")

                signal_tools.append(tc.name)
                break

        # 2. Execute Non-Intercepted Tools
        remaining_tool_calls = [tc for tc in tool_calls if tc.name not in signal_tools]

        tool_results = []
        if remaining_tool_calls:
            # Execute Tools using shared AgentToolExecutor
            tool_executor = self._tool_executor_class(
                tool_map=tool_map,
                state=state,
                config=config,
                name=name,
                enable_diff_tracking=self._enable_diff_tracking,
            )

            async def _execute_tool(tc: ToolCall) -> "ToolExecutionResult":
                return await tool_executor.execute_tool(
                    tool_name=tc.name,
                    tool_args=tc.args,
                    tool_id=tc.id,
                    local_tool_history=local_tool_history,
                )

            # Execute tools (Single-shot subtasks often call multiple independent tools)
            if parallel_tools:
                logger.info(f"[{name}] ⚡ Executing {len(remaining_tool_calls)} tools in parallel")
                tool_results = await asyncio.gather(*[_execute_tool(tc) for tc in remaining_tool_calls])
            else:
                logger.info(f"[{name}] ⛓️ Executing {len(remaining_tool_calls)} tools sequentially")
                for tc in remaining_tool_calls:
                    res = await _execute_tool(tc)
                    tool_results.append(res)

            for res in tool_results:
                tool_msg = res.message
                raw_content = res.raw_result
                logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:300])}...")
                new_messages.append(tool_msg)
                
                # 3.1 Post-Execution Signal Detection
                if not pending_signal:
                    signal = signal_manager.detect_post_execution_signal(tool_msg.name, raw_content)
                    if signal:
                        pending_signal = signal

        # 3. Protocol Violation Check (Subtask MUST result in a signal or tool execution)
        if not pending_signal and not tool_calls:
            logger.error(f"[{name}] 🛑 SINGLE-SHOT VIOLATION: Subtask did not call any tool!")
            error_msg = AIMessage(content="Subtask failed: No tool was invoked.")
            new_messages.append(error_msg)
            return EngineResult(
                messages=new_messages,
                tool_history=local_tool_history,
                blackboard=state.blackboard,
            )

        logger.info(f"[{name}] ✓ Single-shot complete. {len(response.tool_calls)} tool(s) executed.")

        return EngineResult(
            messages=new_messages,
            tool_history=local_tool_history,
            blackboard=state.blackboard,
            signal=pending_signal,
        )

    def _build_system_messages(self, system_prompt: str, messages: list, provider: str) -> list[BaseMessage]:
        """
        Builds system messages optimized for Prompt Caching.
        Decouples static instructions from dynamic telemetry to maximize cache hit rates.
        """
        # 2. Provider-specific optimization
        # Use nested list structure (Anthropic format) ONLY for pure anthropic providers.
        # For Kimi (routing via OpenAI gateway) or others, use standard string content.
        # Caching on OpenAI-compatible providers is usually achieved by keeping the prefix static.
        if provider == "anthropic":
            return [SystemMessage(content=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ])]
        else:
            # Standard string content for Moonshot/Kimi/DeepSeek/OpenAI
            return [SystemMessage(content=system_prompt)]

    def _handle_llm_exception(self, e: Exception, name: str, state: AgentState) -> EngineResult:
        """Centralized handling for LLM invocation exceptions using LLMErrorHandler."""
        from app.core.engine.error_handler import LLMErrorHandler
        from app.i18n.service import i18n

        logger.error(f"[{name}] LLM invocation failed: {e}")

        # Use the centralized classifier
        classification = LLMErrorHandler.classify_exception(e)

        # Bubble up terminal errors to trigger specialized UI (quota/auth) in the background orchestrator
        if classification.is_terminal:
            logger.warning(f"[{name}] Terminal LLM error detected ({classification.error_type}). Bubbling up to orchestrator.")
            raise e

        icon_failed = i18n.get("icons.failed") or "❌"

        # Construct a rich error message for the AI message content
        user_friendly_msg = (
            f"{icon_failed} **{classification.title}**: "
            f"{classification.message}\n\n"
            f"{classification.hint}\n\n"
            f"> {classification.raw_error[:200]}"
        )

        return EngineResult(
            messages=[AIMessage(
                content=user_friendly_msg,
                metadata={
                    "is_error": True,
                    "error_type": classification.error_type,
                    "status_code": classification.status_code,
                    "raw_error": classification.raw_error
                }
            )],
            tool_history=[],
            blackboard=state.blackboard,
        )

    def _parse_inferred_blackboard(self, content: Any, blackboard: Optional[BlackboardState], name: str) -> BlackboardState:
        """
        Parses the LLM response content for inferred blackboard updates.
        Returns updated blackboard without modifying input state directly.
        """
        if not content or not isinstance(content, str):
            return blackboard or BlackboardState()

        # Support [BLACKBOARD: key=value] pattern
        # Optimized to support multi-line values and handle greedy matching more safely
        pattern = r"\[BLACKBOARD:\s*(\w+)\s*=\s*(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            blackboard = blackboard or BlackboardState()
            metadata_updates = {}

            for key, val in matches:
                val_str = val.strip()
                if val_str.lower() == "true":
                    val = True
                elif val_str.lower() == "false":
                    val = False
                elif val_str.isdigit():
                    val = int(val_str)
                else:
                    val = val_str

                metadata_updates[key] = val
                logger.info(f"[{name}] 🖊️ Blackboard field '{key}' updated via Inference: {val}")

            blackboard.metadata = blackboard.metadata.model_copy(
                update=metadata_updates
            )

        return blackboard or BlackboardState()


# Global default instance for backward compatibility
_default_engine: AgentEngine | None = None


def get_default_engine() -> AgentEngine:
    """Get or create the default global AgentEngine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = AgentEngine()
    return _default_engine


def set_default_engine(engine: AgentEngine) -> None:
    """Set the default global AgentEngine instance (for testing)."""
    global _default_engine
    _default_engine = engine
