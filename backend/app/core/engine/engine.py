"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.
"""

import logging
from typing import Any

from app.core.engine.callbacks.database_logger import current_node_source
from app.core.engine.context_trimmer import ContextTrimmer
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.schemas import EngineResult, NodeOutcome
from app.core.engine.signals import signal_manager
from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.core.memory.tool_output_memory import get_tool_memory_from_state
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class AgentEngine:
    """
    Instance-based execution engine for EvoLoop Agents.
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
        self._llm_factory = llm_factory or LLMFactory
        self._config_service = config_service
        self._tool_executor_class = tool_executor_class
        self._enable_diff_tracking = enable_diff_tracking
        self._context_trimmer = context_trimmer or ContextTrimmer()
        self._inference_engine = inference_engine or InferenceEngine(
            llm_factory=self._llm_factory,
            context_trimmer=self._context_trimmer,
        )
        self._signal_registry = signal_registry or signal_manager

    async def run_node(
        self,
        state: AgentState,
        config: dict,
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
        if not model:
            raise ValueError(
                f"[{name}] No model provided for node execution."
            )

        llm, provider = await self._inference_engine.create_llm(
            model=model,
            temperature=temperature,
        )
        llm_with_tools, tool_map = self._inference_engine.bind_tools(llm, tools)

        tool_memory = get_tool_memory_from_state(state)
        trim_result = self._context_trimmer.trim(
            messages=state.messages,
            model=model,
            node_source=node_source or name.lower(),
            tool_memory=tool_memory,
            is_retry=state.is_retry or False,
        )
        repaired_messages = trim_result.messages

        tool_executor = _ToolExecutorAdapter(
            tool_executor_class=self._tool_executor_class,
            tool_map=tool_map,
            state=state,
            config=config,
            name=name,
            enable_diff_tracking=self._enable_diff_tracking,
            parallel=parallel_tools,
        )

        interceptors = self._signal_registry.build_interceptors()

        current_node_source.set(node_source or name.lower())

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
                iteration_count=state.iteration_count,
            )

        outcome_status = "success"
        if inference_result.get("is_truncated"):
            outcome_status = "truncated"
        elif inference_result.get("signal"):
            outcome_status = "interrupted"
        last_msg = inference_result.get("messages", [])[-1] if inference_result.get("messages") else None
        if last_msg and last_msg.role == "assistant" and last_msg.additional_kwargs.get("is_error"):
            outcome_status = "error"

        outcome = NodeOutcome(status=outcome_status)

        result = EngineResult(
            messages=inference_result.get("messages", []),
            tool_history=inference_result.get("tool_history", []),
            is_truncated=inference_result.get("is_truncated", False),
            signal=inference_result.get("signal"),
            outcome=outcome,
            queued_signals=inference_result.get("queued_signals", []),
        )

        if node_source:
            for msg in inference_result.get("messages", []):
                if msg.additional_kwargs is None:
                    msg.additional_kwargs = {}
                msg.additional_kwargs["node_source"] = node_source

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
        config: dict,
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

    async def execute_batch(self, tool_calls: list[dict], local_tool_history: list[str]) -> tuple[list[Any], Any | None]:
        return await self._executor.execute_batch(tool_calls, local_tool_history, parallel=self._parallel)


_default_engine: AgentEngine | None = None


def get_default_engine() -> AgentEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AgentEngine()
    return _default_engine


def set_default_engine(engine: AgentEngine) -> None:
    global _default_engine
    _default_engine = engine
