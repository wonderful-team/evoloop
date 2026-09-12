"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.
"""

import logging
from collections.abc import Callable
from typing import Any

from app.core.channel.policy import current_session_source
from app.core.context.manager import ContextManager
from app.core.engine.constants import MAX_STEPS
from app.core.engine.context_trimmer import ContextTrimmer
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.message.constants import MessageRole
from app.core.engine.schemas import EngineResult, RunOutcome, RunOutcomeStatus
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

    async def run_react_loop(
        self,
        state: AgentState,
        config: dict,
        system_prompt: str,
        tools: list[Any],
        max_steps: int = MAX_STEPS,
        temperature: float = 0.7,
        name: str = "Agent",
        parallel_tools: bool = False,
        model: str | None = None,
        steer_provider: Callable | None = None,
    ) -> EngineResult:
        """Executes the standard Agent ReAct loop."""
        if not model:
            logger.info(
                f"[{name}] No model provided; relying on cloud gateway default model routing."
            )

        llm, _provider = await self._inference_engine.create_llm(
            model=model,
            temperature=temperature,
        )
        llm_with_tools, tool_map = self._inference_engine.bind_tools(llm, tools)

        tool_memory = get_tool_memory_from_state(state)
        trim_result = self._context_trimmer.trim(
            messages=state.messages,
            model=model,
            tool_memory=tool_memory,
            is_retry=state.is_retry or False,
        )
        repaired_messages = trim_result.messages

        tool_executor = ToolExecutorAdapter(
            tool_executor_class=self._tool_executor_class,
            tool_map=tool_map,
            state=state,
            config=config,
            name=name,
            enable_diff_tracking=self._enable_diff_tracking,
            parallel=parallel_tools,
        )

        # Propagate session source ("voice"/"web"/"mobile") for OutputChannelPolicy.
        _ctx = ContextManager.current()
        current_session_source.set(getattr(_ctx.metadata, "source", None))

        async def _rebind() -> tuple:
            """skill 激活包后重算工具面并重新绑定（同 run 内立即可用）。"""
            from app.core.tools.manager import tool_manager as _tm

            refreshed = await _tm.get_agent_tools("react", state)
            return self._inference_engine.bind_tools(llm, refreshed)

        inference_result = await self._inference_engine.run_react_loop(
            llm_with_tools=llm_with_tools,
            messages=repaired_messages,
            system_prompt=system_prompt,
            config=config,
            name=name,
            max_steps=max_steps,
            tool_executor=tool_executor,
            model=model,
            iteration_count=state.iteration_count,
            steer_provider=steer_provider,
            rebind=_rebind,
        )

        outcome_status = RunOutcomeStatus.SUCCESS
        if inference_result.get("is_truncated"):
            outcome_status = RunOutcomeStatus.TRUNCATED
        last_msg = (
            inference_result.get("messages", [])[-1]
            if inference_result.get("messages")
            else None
        )
        if (
            last_msg
            and last_msg.role == MessageRole.AI
            and last_msg.additional_kwargs.get("is_error")
        ):
            outcome_status = RunOutcomeStatus.ERROR

        outcome = RunOutcome(status=outcome_status)

        result = EngineResult(
            messages=inference_result.get("messages", []),
            tool_history=inference_result.get("tool_history", []),
            is_truncated=inference_result.get("is_truncated", False),
            outcome=outcome,
        )

        return result


class ToolExecutorAdapter:
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

    def update_tool_map(self, tool_map: dict) -> None:
        """Run 中途刷新工具面（skill 激活包后同 run 可用）。"""
        self._executor.tool_map = tool_map

    async def execute_batch(self, tool_calls: list[dict], local_tool_history: list[str]) -> list[Any]:
        return await self._executor.execute_batch(
            tool_calls, local_tool_history, parallel=self._parallel
        )


_default_engine: AgentEngine | None = None


def get_default_engine() -> AgentEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AgentEngine()
    return _default_engine


def set_default_engine(engine: AgentEngine) -> None:
    global _default_engine
    _default_engine = engine
