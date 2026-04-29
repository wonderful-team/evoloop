import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.schemas import EngineResult
from app.core.engine.message.utils import get_last_human_message
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.prompts import SupervisorContext, SupervisorPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class SupervisorNode(BaseAgentNode):
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent (LLM-First Architecture).

    Responsibilities:
    1. Sense environment via tools (telemetry, search_native_tools, search_skills)
    2. LLM-driven routing decisions via ReAct loop
    3. Tool authorization via authorized_tools
    4. Context building (tools, memory, project structure)
    """

    def __init__(self):
        super().__init__(node_name="Supervisor", max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS, temperature=0.2)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        """Pre-computation: Check for subtask completion and worker outcome."""
        # NOTE: Message cleanup (including trailing error pruning) is now handled
        # uniformly by ContextTrimmer in engine.run_node(). SupervisorNode should
        # not perform ad-hoc message manipulation here.

        # Consume stale routing and plans from previous turns
        from app.core.engine.state.lifecycle import StateLifecycleManager
        StateLifecycleManager.consume_next_node(state)
        StateLifecycleManager.consume_spawn_plan(state)

        # Optional: Emit initial status
        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        # 1. Aggregate Parallel Results
        blackboard = state.blackboard
        subtask_results = blackboard.subtask_results
        pending_agg = blackboard.pending_aggregation

        if pending_agg and pending_agg.expected_count:
            expected = pending_agg.expected_count
            if len(subtask_results) >= expected:
                logger.info(f"[Supervisor] 🧩 All {expected} subtasks done. Routing to Aggregator.")
                return StateUpdate(next_node=RoutingTarget.AGGREGATOR)

        # 2. Check Worker/Aggregator Outcome
        worker_outcome = StateLifecycleManager.consume_worker_outcome(state)
        if worker_outcome:
            if worker_outcome == "success":
                logger.info("[Supervisor] ✅ Task complete. Routing to FINISH.")
                return StateUpdate(
                    next_node=RoutingTarget.FINISH,
                    blackboard=blackboard,
                    iteration_count=(state.iteration_count or 0) + 1
                )
            else:
                logger.warning(f"[Supervisor] 🔄 Worker outcome: {worker_outcome}. Re-planning required.")
                blackboard.ticket = None

        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """Construct (Static Instructions, Dynamic Context Ticket)."""
        project_id = (state.project_id or DEFAULT_PROJECT_ID)
        messages = list(state.messages)

        # Build logical context for the prompt builder
        context = await self._build_context(state, config, messages, project_id)

        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context.iteration_count,
            context=context,
        )
        # Static Prompt (Cacheable)
        static_system_prompt = await prompt_builder.build(config)
        # Dynamic Ticket (Injected via HumanMessage in BaseAgentNode)
        dynamic_context_ticket = await prompt_builder.build_context_ticket(config, session_goal=state.session_goal)

        return static_system_prompt, dynamic_context_ticket

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Load core routing tools."""
        return await tool_manager.get_node_tools("supervisor", state)

    async def _customize_dispatch_result(
        self,
        dispatch_result: StateUpdate,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Inject iteration_count into signal dispatch results."""
        new_iter_count = (original_state.iteration_count or 0) + 1
        if isinstance(dispatch_result, StateUpdate):
            dispatch_result.iteration_count = new_iter_count
        return dispatch_result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Supervisor-specific protocol checks when no signal is present."""
        new_iter_count = (original_state.iteration_count or 0) + 1
        new_messages = [
            m for m in (engine_result.messages or [])
            if m.name != "context_ticket"
        ]
        blackboard = engine_result.blackboard or original_state.blackboard

        # Check for infrastructure errors
        has_error_msg = any(
            msg.additional_kwargs.get("is_error") for msg in new_messages
        )
        if has_error_msg:
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.FINISH,
                blackboard=blackboard,
                iteration_count=new_iter_count,
            )

        # Handle "Silent" Protocol Violation - fallback to CHAT if there is content
        ai_content = ""
        last_msg = new_messages[-1] if new_messages else None
        
        if isinstance(last_msg, AIMessage):
            ai_content = str(last_msg.content).strip()

        if ai_content:
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.CHAT,
                blackboard=blackboard,
                iteration_count=new_iter_count,
            )

        # Diagnostic: Why are we stopping?
        logger.error(
            f"[Supervisor] 🛑 Stop: No routing signal and no content. "
            f"Last message type: {type(last_msg).__name__ if last_msg else 'None'}. "
            f"Content length: {len(ai_content)}. "
            f"Has tool_calls: {bool(getattr(last_msg, 'tool_calls', []))}. "
            f"Additional Kwargs Keys: {list(last_msg.additional_kwargs.keys()) if hasattr(last_msg, 'additional_kwargs') else 'N/A'}"
        )
        
        return StateUpdate(
            messages=new_messages,
            next_node=RoutingTarget.FINISH,
            blackboard=blackboard,
            iteration_count=new_iter_count
        )

    async def _emit_status(self, config: RunnableConfig, status: str):
        """Emit status update via activity_monitor."""
        try:
            from app.core.monitoring.activity import activity_monitor
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            await activity_monitor.update_agent_state(
                thread_id=thread_id,
                mode="PLANNING",
                task_name="Supervisor Decision",
                task_status=status,
            )
        except Exception as e:
            logger.warning(f"[Supervisor] Failed to emit status update: {e}")

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> "SupervisorContext":
        """Simplified context builder for LLM planning (Phase 1)."""
        # 1. Get Core Routing Tools — re-use get_tools() result to avoid double-loading
        core_tools = await self.get_tools(state)
        last_msg = get_last_human_message(messages)

        # Get blackboard from state for prompt builder
        blackboard = state.blackboard

        return SupervisorContext(
            tools=core_tools,
            iteration_count=(state.iteration_count or 0),
            last_human_msg=last_msg,
            blackboard=blackboard,
            structured_plan=state.structured_plan or state.current_plan,
        )
