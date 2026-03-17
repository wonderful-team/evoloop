"""
Supervisor Node - ReAct Architecture

The Supervisor is the decision-making hub of the EvoLoop system.
It analyzes user input, routes to specialized nodes via the route_to tool.
"""
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine import AgentEngine
from app.core.engine.message_utils import get_message_text, get_last_human_message
from app.core.engine.state import AgentState
from app.core.memory import memory_manager
from app.core.tools.manager import tool_manager
from app.constants import DEFAULT_PROJECT_ID, RoutingTarget
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


# ===== v5 UNIFIED ROUTING =====
# ROLE_CONFIGS removed. Routing is fully YAML + Skill SOP driven.
# The Supervisor LLM must call route_to('worker', context={agent_config:{...}})
# for all execution roles. Role personas and SOPs live in:
#   app/core/learning/skills/roles/*.SKILL.md
# Fixed nodes (finish, documenter, chat) route directly via YAML edges.
# Note: Prompt construction logic moved to SupervisorPromptBuilder


class SupervisorNode:
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent (LLM-First Architecture).

    Responsibilities:
    1. Sense environment via tools (telemetry, search_native_tools, search_skills)
    2. LLM-driven routing decisions via ReAct loop
    3. Tool authorization via authorized_tools
    4. Context building (tools, memory, project structure)
    """

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Main entry point for the Supervisor node (ReAct Architecture)."""
        project_id = state.get("project_id", DEFAULT_PROJECT_ID)
        messages = list(state.get("messages", []))
        if not messages:
            logger.warning("[Supervisor] No messages found in state. Exiting.")
            return {"next_node": RoutingTarget.FINISH}

        # Phase 0: Ticket Cleanup (Blackboard Lifecycle)
        # We ensure any stale ticket from a previous specialist run is cleared
        # so it doesn't pollute the Supervisor's prompt or next routing.
        cleanup_state = {}
        if state.get("execution_ticket"):
            logger.info("[Supervisor] 🧹 Clearing stale ExecutionTicket")
            cleanup_state["execution_ticket"] = None

        # Emit initial status
        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        # Phase 1: Aggregate Parallel Results (New Blackboard Integration)
        blackboard = state.get("blackboard") or {}
        subtask_results = blackboard.get("subtask_results", [])
        pending_agg = blackboard.get("pending_aggregation", {})

        if pending_agg:
            expected = pending_agg.get("expected_count", 0)
            if len(subtask_results) >= expected:
                logger.info(f"[Supervisor] 🧩 All {expected} subtasks done. Routing to Aggregator.")
                return {
                    "next_node": RoutingTarget.AGGREGATOR,
                    "blackboard": blackboard
                }

        # Phase 2: Build Context (Simplified via Middleware)
        context = await self._build_context(state, config, messages, project_id)

        # Phase 3: Single ReAct Loop (Routing tools now provided via agent_main.yaml)
        tools = context["tools"]

        # Use Builder for unified prompt construction
        from app.core.engine.prompts import SupervisorPromptBuilder

        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context["iteration_count"],
            context=context,
        )
        dynamic_prompt = await prompt_builder.build(config)

        engine_result = await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=dynamic_prompt,
            tools=tools,
            max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS,
            name="Supervisor",
        )

        # Increment logical iteration counter
        current_iterations = state.get("iteration_count", 0)
        new_iter_count = current_iterations + 1

        # Phase 4: Unified Dispatching (Phase 2)
        signal = engine_result.get("signal")
        if signal:
            from app.core.engine.dispatcher import SignalDispatcher
            dispatch_result = await SignalDispatcher.dispatch(state, signal, config)
            if isinstance(dispatch_result, dict):
                dispatch_result["iteration_count"] = new_iter_count
            return dispatch_result

        # Legacy/Fallback Handling
        new_messages = engine_result.get("messages", [])
        blackboard = engine_result.get("blackboard", blackboard)
        
        if new_messages:
            last_msg = new_messages[-1]
            if isinstance(last_msg, AIMessage) and not getattr(last_msg, "tool_calls", None):
                # Pure text response = consider task complete
                logger.info("[Supervisor] 🏁 Text response without routing - finishing.")
                return {
                    "messages": new_messages,
                    "next_node": RoutingTarget.FINISH,
                    "blackboard": blackboard,
                    "iteration_count": new_iter_count
                }

        # Ultimate fallback: default to Worker
        logger.warning("[Supervisor] ⚠️ No routing signal and no text response - defaulting to Worker")
        return {
            "messages": new_messages,
            "next_node": RoutingTarget.WORKER,
            "blackboard": blackboard,
            "iteration_count": new_iter_count
        }

    async def _emit_status(self, config: RunnableConfig, status: str):
        """Emit status update for UI responsiveness."""
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

        logger.info(f"[Supervisor] 📂 Context utilized from unified Middleware.")

        # Get blackboard from state for prompt builder
        blackboard = state.get("blackboard") or {}

        return {
            "tools": core_tools,
            "iteration_count": state.get("iteration_count", 0),
            "last_human_msg": last_msg,
            "blackboard": blackboard,
            "current_plan": state.get("current_plan"),
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
