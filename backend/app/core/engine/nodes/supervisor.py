import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine import get_default_engine
from app.core.engine.message_utils import get_last_human_message
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager
from app.constants import DEFAULT_PROJECT_ID
from app.i18n.service import i18n
from app.core.engine.nodes.base import BaseAgentNode

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
        # Clean stale routing and outcomes from previous turns
        state["next_node"] = None
        if "blackboard" in state and state["blackboard"]:
            state["blackboard"]["worker_outcome"] = None
        
        # Optional: Emit initial status
        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        # 1. Aggregate Parallel Results
        blackboard = state.get("blackboard") or {}
        subtask_results = blackboard.get("subtask_results", [])
        pending_agg = blackboard.get("pending_aggregation", {})

        if pending_agg and pending_agg.get("expected_count"):
            expected = pending_agg["expected_count"]
            if len(subtask_results) >= expected:
                logger.info(f"[Supervisor] 🧩 All {expected} subtasks done. Routing to Aggregator.")
                return StateUpdate(next_node=RoutingTarget.AGGREGATOR)

        # 2. Check Worker/Aggregator Outcome
        worker_outcome = blackboard.get("worker_outcome")
        if worker_outcome:
            # Consume the signal
            blackboard["worker_outcome"] = None
            if worker_outcome == "success":
                logger.info("[Supervisor] ✅ Task complete. Routing to FINISH.")
                return StateUpdate(
                    next_node=RoutingTarget.FINISH,
                    blackboard=blackboard,
                    iteration_count=state.get("iteration_count", 0) + 1
                )
            else:
                logger.warning(f"[Supervisor] 🔄 Worker outcome: {worker_outcome}. Re-planning required.")
                blackboard["ticket"] = None
        
        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """Construct (Static Instructions, Dynamic Context Ticket)."""
        from app.core.engine.prompts import SupervisorPromptBuilder
        project_id = state.get("project_id", DEFAULT_PROJECT_ID)
        messages = state.get("messages", [])
        
        # Build logical context for the prompt builder
        context = await self._build_context(state, config, messages, project_id)
        
        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context["iteration_count"],
            context=context,
        )
        # Static Prompt (Cacheable)
        static_system_prompt = await prompt_builder.build(config)
        # Dynamic Ticket (Injected via HumanMessage in BaseAgentNode)
        dynamic_context_ticket = await prompt_builder.build_context_ticket(config)
        
        return static_system_prompt, dynamic_context_ticket

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Load core routing tools."""
        return await asyncio.to_thread(tool_manager.get_node_tools, "supervisor", state)

    async def handle_outcome(self, original_state: AgentState, engine_result: dict[str, Any], config: RunnableConfig) -> StateUpdate:
        """Signal handling and protocol verification."""
        # 1. Base Signal/Dispatcher Handling
        signal = engine_result.get("signal")
        new_iter_count = original_state.get("iteration_count", 0) + 1
        
        if signal:
            from app.core.engine.dispatcher import SignalDispatcher
            dispatch_result = await SignalDispatcher.dispatch(original_state, signal, config)
            if isinstance(dispatch_result, StateUpdate):
                dispatch_result.iteration_count = new_iter_count
            elif isinstance(dispatch_result, dict):
                dispatch_result["iteration_count"] = new_iter_count
            return dispatch_result

        # 2. Protocol Violation Check (Supervisor MUST route or be an error)
        new_messages = engine_result.get("messages", [])
        blackboard = engine_result.get("blackboard", original_state.get("blackboard", {}))
        
        # Check for infrastructure errors
        has_error_msg = any(
            getattr(msg, "metadata", {}).get("is_error") for msg in new_messages
            if hasattr(msg, "metadata")
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
        if new_messages and isinstance(new_messages[-1], AIMessage):
            ai_content = str(new_messages[-1].content).strip()
            
        if ai_content:
            logger.warning("[Supervisor] ⚠️ Protocol violation: No route_to but returned content. Falling back to 'chat'.")
            return StateUpdate(
                next_node=RoutingTarget.CHAT,
                blackboard=blackboard,
                iteration_count=new_iter_count,
            )

        logger.error("[Supervisor] 🛑 Stop: No routing signal and no content.")
        return StateUpdate(
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
        except Exception:
            pass

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> dict[str, Any]:
        """Simplified context builder for LLM planning (Phase 1)."""
        # 1. Get Core Routing Tools
        core_tools = tool_manager.get_node_tools("supervisor", state)
        last_msg = get_last_human_message(messages)

        # Get blackboard from state for prompt builder
        blackboard = state.get("blackboard") or {}

        return {
            "tools": core_tools,
            "iteration_count": state.get("iteration_count", 0),
            "last_human_msg": last_msg,
            "blackboard": blackboard,
            "current_plan": state.get("current_plan") or state.get("structured_plan"),
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> StateUpdate:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
