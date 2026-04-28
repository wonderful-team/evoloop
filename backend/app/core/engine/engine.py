"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.

This module provides the main AgentEngine class as a thin facade that
orchestrates:
- ContextTrimmer (unified token-driven message trimming)
- InferenceEngine (LLM ReAct / single-shot loops)
- SignalRegistry (plugin-based signal interception)
- BlackboardParser (structured blackboard updates from LLM output)

Supports dependency injection for easier testing and extensibility.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.blackboard_parser import BlackboardParser
from app.core.engine.context_trimmer import ContextTrimmer
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.schemas import EngineResult, NodeOutcome
from app.core.engine.signals.registry import get_default_registry
from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.core.exceptions import InferenceError
from app.core.memory.tool_output_memory import get_tool_memory_from_state
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class AgentEngine:
    """
    Instance-based execution engine for EvoLoop Agents.

    Supports dependency injection for easier testing and extensibility.
    """

    def __init__(
        self,
        llm_factory: Any | None = None,
        config_service: Any | None = None,
        tool_executor_class: type = AgentToolExecutor,
        enable_diff_tracking: bool = True,
        inference_engine: InferenceEngine | None = None,
        context_trimmer: ContextTrimmer | None = None,
        signal_registry=None,
    ):
        """
        Initialize AgentEngine with optional dependency injection.

        Args:
            llm_factory: Optional LLM factory (defaults to LLMFactory)
            config_service: Optional config service (defaults to SystemConfigService)
            tool_executor_class: Tool executor class (defaults to AgentToolExecutor)
            enable_diff_tracking: Whether to enable diff tracking for file operations
            inference_engine: Optional custom InferenceEngine
            context_trimmer: Optional custom ContextTrimmer
            signal_registry: Optional custom SignalRegistry
        """
        self._llm_factory = llm_factory or LLMFactory
        self._config_service = config_service
        self._tool_executor_class = tool_executor_class
        self._enable_diff_tracking = enable_diff_tracking
        self._context_trimmer = context_trimmer or ContextTrimmer()
        self._inference_engine = inference_engine or InferenceEngine(
            llm_factory=self._llm_factory,
            context_trimmer=self._context_trimmer,
        )
        self._signal_registry = signal_registry or get_default_registry()

    async def run_node(
        self,
        state: AgentState,
        config: RunnableConfig,
        system_prompt: str,
        tools: list[Any],
        max_steps: int = 5,
        temperature: float = 0.7,
        name: str = "Agent",
        is_subtask: bool = False,
        node_source: str = None,
        parallel_tools: bool = False,
        model: str | None = None,
    ) -> EngineResult:
        """Executes the standard Agent ReAct loop."""
        # 1. Resolve model (must be explicitly provided)
        if not model:
            raise ValueError(
                f"[{name}] No model provided for node execution. "
                "Please pass 'model' explicitly to engine.run_node()."
            )

        # 2. Initialize LLM
        llm, provider = await self._inference_engine.create_llm(
            model=model,
            temperature=temperature,
        )
        llm_with_tools, tool_map = self._inference_engine.bind_tools(llm, tools)

        # 3. Message Preparation (forgotten, windowing, repair)
        tool_memory = get_tool_memory_from_state(state)
        trim_result = self._context_trimmer.trim(
            messages=state.messages,
            model=model,
            node_source=node_source or name.lower(),
            tool_memory=tool_memory,
            is_retry=getattr(state, "is_retry", False),
        )
        repaired_messages = trim_result.messages

        # 4. Build tool executor wrapper for InferenceEngine
        tool_executor = _ToolExecutorAdapter(
            tool_executor_class=self._tool_executor_class,
            tool_map=tool_map,
            state=state,
            config=config,
            name=name,
            enable_diff_tracking=self._enable_diff_tracking,
            parallel=parallel_tools,
        )

        # 5. Build interceptors from SignalRegistry
        interceptors = self._signal_registry.build_interceptors()

        # 6. Run inference
        try:
            if is_subtask:
                inference_result = await self._inference_engine.run_single_shot(
                    llm_with_tools=llm_with_tools,
                    messages=repaired_messages,
                    system_prompt=system_prompt,
                    provider=provider,
                    config=config,
                    name=name,
                    tool_executor=tool_executor,
                )
            else:
                inference_result = await self._inference_engine.run_react_loop(
                    llm_with_tools=llm_with_tools,
                    messages=repaired_messages,
                    system_prompt=system_prompt,
                    provider=provider,
                    config=config,
                    name=name,
                    max_steps=max_steps,
                    tool_executor=tool_executor,
                    interceptors=interceptors,
                    model=model,
                )
        except InferenceError as ie:
            return EngineResult(
                messages=[AIMessage(
                    content=ie.user_friendly_msg,
                    metadata={
                        "is_error": True,
                        "error_type": ie.error_type,
                        "status_code": ie.status_code,
                        "raw_error": ie.raw_error,
                    }
                )],
                tool_history=[],
                blackboard=state.blackboard,
            )

        # 7. Parse blackboard updates from final response content
        last_response = inference_result.get("last_response")
        blackboard = state.blackboard
        if last_response and last_response.content:
            blackboard = BlackboardParser.parse(
                last_response.content,
                blackboard,
                name=name,
            )

        # 8. Determine structured outcome
        outcome_status = "success"
        if inference_result.get("is_truncated"):
            outcome_status = "truncated"
        elif inference_result.get("signal"):
            outcome_status = "interrupted"
        last_msg = inference_result.get("messages", [])[-1] if inference_result.get("messages") else None
        if last_msg and isinstance(last_msg, AIMessage) and getattr(last_msg, "metadata", {}).get("is_error"):
            outcome_status = "error"

        outcome = NodeOutcome(status=outcome_status)

        # 9. Build EngineResult
        # Extract routing_target from last_response metadata if signal is not present
        routing_target = None
        if not inference_result.get("signal") and last_response and hasattr(last_response, "metadata"):
            routing_target = (last_response.metadata or {}).get("routing_target")

        result = EngineResult(
            messages=inference_result.get("messages", []),
            tool_history=inference_result.get("tool_history", []),
            blackboard=blackboard,
            is_truncated=inference_result.get("is_truncated", False),
            signal=inference_result.get("signal"),
            routing_target=routing_target,
            outcome=outcome,
        )

        # Add node_source marker to AI messages
        if node_source:
            for msg in result.messages or []:
                if isinstance(msg, AIMessage) and msg.content:
                    if not hasattr(msg, "metadata") or msg.metadata is None:
                        msg.metadata = {}
                    msg.metadata["node_source"] = node_source

        return result


class _ToolExecutorAdapter:
    """
    Adapts AgentToolExecutor to the batch interface expected by InferenceEngine.
    """

    def __init__(
        self,
        tool_executor_class: type,
        tool_map: dict,
        state: AgentState,
        config: RunnableConfig,
        name: str,
        enable_diff_tracking: bool,
        parallel: bool,
    ):
        self._executor = tool_executor_class(
            tool_map=tool_map,
            state=state,
            config=config,
            name=name,
            enable_diff_tracking=enable_diff_tracking,
        )
        self._parallel = parallel

    async def execute_batch(self, tool_calls: list[dict], local_tool_history: list[str]) -> list[Any]:
        return await self._executor.execute_batch(tool_calls, local_tool_history, parallel=self._parallel)


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
