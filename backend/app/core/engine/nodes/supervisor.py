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
# Note: memory_manager is no longer imported globally. Use container.memory_manager() when needed.
from app.core.tools.manager import tool_manager
from app.constants import DEFAULT_PROJECT_ID, RoutingTarget
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


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
        # Unified Hydration (Phase 1 Optimization)
        from app.core.engine.context_hydrator import EvoContextMiddleware
        state = await EvoContextMiddleware.hydrate(state, config)
        logger.info("[Supervisor] 📂 Context utilized from unified Middleware.")

        if not messages:
            logger.warning("[Supervisor] No messages found in state. Exiting.")
            return {"next_node": RoutingTarget.FINISH}

        # Emit initial status
        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        # Phase 1: Aggregate Parallel Results (New Blackboard Integration)
        blackboard = state.get("blackboard") or {}
        subtask_results = blackboard.get("subtask_results", [])
        pending_agg = blackboard.get("pending_aggregation", {})

        if pending_agg and pending_agg.get("expected_count"):
            expected = pending_agg["expected_count"]
            if len(subtask_results) >= expected:
                logger.info(f"[Supervisor] 🧩 All {expected} subtasks done. Routing to Aggregator.")
                return {
                    "next_node": RoutingTarget.AGGREGATOR,
                    "blackboard": blackboard
                }

        # Phase 2: Check Worker/Aggregator Outcome (Structured Control Flow)
        worker_outcome = blackboard.get("worker_outcome")
        if worker_outcome:
            # Consume the signal to prevent stale detection on next iteration
            blackboard["worker_outcome"] = None

            if worker_outcome == "success":
                logger.info("[Supervisor] ✅ Task complete (structured outcome). Routing to FINISH.")
                return {
                    "next_node": RoutingTarget.FINISH,
                    "blackboard": blackboard,
                    "iteration_count": state.get("iteration_count", 0) + 1
                }
            else:
                # Task incomplete/failed - re-plan via LLM
                logger.warning(f"[Supervisor] 🔄 Worker outcome: {worker_outcome}. Re-planning required.")
                blackboard["ticket"] = None
                # Fall through to LLM decision below

        # Build Context and Run LLM Decision Loop
        context = await self._build_context(state, config, messages, project_id)

        # Single ReAct Loop (Routing tools now provided via agent_main.yaml)
        tools = context["tools"]

        # Use Builder for unified prompt construction
        from app.core.engine.prompts import SupervisorPromptBuilder

        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context["iteration_count"],
            context=context,
        )
        dynamic_prompt = await prompt_builder.build(config)

        # Get user selected model from config (if any)
        model = config.get("configurable", {}).get("model")

        engine_result = await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=dynamic_prompt,
            tools=tools,
            model=model,  # Use user selected model
            max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS,
            name="Supervisor",
            temperature=0.2,  # Balanced: strict tool calling + natural clarification
            node_source="supervisor",  # 👈 标记为 supervisor 节点
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

        # Protocol Violation: Supervisor MUST call route_to (signal)
        new_messages = engine_result.get("messages", [])
        blackboard = engine_result.get("blackboard", blackboard)

        logger.error("[Supervisor] 🛑 Protocol violation: No route_to signal in response")
        error_msg = AIMessage(
            content="Error: Supervisor failed to determine next action."
        )
        return {
            "messages": new_messages + [error_msg],
            "next_node": RoutingTarget.FINISH,
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
