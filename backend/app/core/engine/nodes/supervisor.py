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

from app.core.engine import AgentEngine
from app.core.engine.message_utils import get_message_text
from app.core.engine.state import AgentState
from app.core.memory import memory_manager
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


# ===== v5 UNIFIED ROUTING =====
# Static role persona configs for auto-generating agent_config when the Supervisor
# routes to a standard role (operator, deep_researcher, etc.).
# The Worker node uses these to adopt the right persona at runtime.
ROLE_CONFIGS = {
    "operator": {
        "role_name": "Workspace Operator",
        "system_instructions": (
            "You are a full-stack systems operator. Execute coding, testing, "
            "and file management tasks. Search for relevant SOPs using "
            "search_skills before complex operations."
        ),
    },
    "deep_researcher": {
        "role_name": "Deep Researcher",
        "system_instructions": (
            "You are an expert analyst. Conduct thorough multi-step research "
            "using file reads, web searches, and codebase exploration. "
            "Synthesize findings into a comprehensive conclusion."
        ),
    },
    "documenter": {
        "role_name": "Documentation Architect",
        "system_instructions": (
            "You are a documentation expert. Manage project docs, wiki pages, "
            "and knowledge harvesting. Read existing docs before creating new ones."
        ),
    },
    "finish": {
        "role_name": "Session Auditor",
        "system_instructions": (
            "You are an acceptance tester. Audit the conversation history against "
            "the mission criteria. Call finalize_session when done, or route_to "
            "operator if incomplete."
        ),
    },
}


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return get_message_text(msg)
    return None


# Note: Prompt construction logic moved to SupervisorPromptBuilder


class SupervisorNode:
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent.

    Responsibilities:
    1. Fast-path routing via IntentClassifier and SkillMatcher
    2. Context building (tools, memory, project structure)
    3. LLM-based planning and exploration
    4. Routing decisions to specialized nodes
    """

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Main entry point for the Supervisor node (ReAct Architecture)."""
        project_id = state.get("project_id", 1)
        messages = list(state.get("messages", []))
        if not messages:
            logger.warning("[Supervisor] No messages found in state. Exiting.")
            return {"next_node": "finish"}

        # Phase 0: Ticket Cleanup (Blackboard Lifecycle)
        # We ensure any stale ticket from a previous specialist run is cleared
        # so it doesn't pollute the Supervisor's prompt or next routing.
        cleanup_state = {}
        if state.get("execution_ticket"):
            logger.info("[Supervisor] 🧹 Clearing stale ExecutionTicket")
            cleanup_state["execution_ticket"] = None

        # Emit initial status
        await self._emit_status(config, i18n.get("prompts.supervisor.status_analyzing"))

        # Phase 0: Context Trimming (Determinstic sliding window)
        trim_result = await self._try_trimming(state)
        if trim_result:
            return trim_result

        # Phase 2: Build Context
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
        dynamic_prompt = prompt_builder.build(config)

        engine_result = await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=dynamic_prompt,
            tools=tools,
            max_steps=100,  # Increased since routing is now part of the loop
            name="Supervisor",
        )

        # Phase 4: Handle routing result
        routing_target = engine_result.get("_routing_target")
        logger.info(f"[Supervisor] Engine result routing target: {routing_target}")

        new_messages = engine_result.get("messages", [])
        if new_messages:
            logger.info(f"[Supervisor] Last engine message: {new_messages[-1].content[:100]}...")

        if routing_target:
            # LLM explicitly called route_to - use its decision
            logger.info(f"[Supervisor] ✅ ReAct routing to: {routing_target}")

            # Solution C: Track visited nodes in scratchpad for loop detection
            existing_scratchpad = state.get("scratchpad", {})
            visited_nodes = existing_scratchpad.get("visited_nodes", [])
            if routing_target not in visited_nodes:
                visited_nodes = visited_nodes + [routing_target]  # Immutable append

            # Extract Context Handoff
            routing_reason = engine_result.get("_routing_reason", "")
            routing_context = engine_result.get("_routing_context", {})

            # Defensive check: ensure routing_context is a dict
            if isinstance(routing_context, str):
                try:
                    routing_context = json.loads(routing_context)
                    if isinstance(routing_context, str):  # Handle double encoding
                        routing_context = json.loads(routing_context)
                except Exception:
                    routing_context = {}

            if not isinstance(routing_context, dict):
                routing_context = {}

            # ===== v5 UNIFIED ROUTING =====
            # Intent-driven Namespace (from LLM)
            inferred_namespace = routing_context.get("namespace_context")

            # All specialist routes now go through the Universal Worker.
            # We auto-generate an agent_config based on the intended role.
            # Resolve the agent_config: either from LLM (worker) or auto-generated (legacy routes)
            if routing_target == "worker":
                agent_config = routing_context.get("agent_config")
                if agent_config and "namespace_context" not in agent_config:
                    agent_config["namespace_context"] = inferred_namespace
            elif routing_target in ROLE_CONFIGS:
                role_cfg = ROLE_CONFIGS[routing_target]
                agent_config = {
                    "role_name": role_cfg["role_name"],
                    "system_instructions": role_cfg["system_instructions"],
                    "tools": [],  # ToolManager will use the YAML profile
                    "namespace_context": inferred_namespace,
                }
                # Redirect to Worker
                routing_target = "worker"
            else:
                agent_config = None

            execution_ticket = {
                "ticket_type": routing_context.get("ticket_type", "task"),
                "priority": routing_context.get("priority", "normal"),
                "focus_paths": routing_context.get("focus_paths", []),
                "topic": routing_context.get("topic") or routing_context.get("query") or routing_reason,
                "acceptance_criteria": routing_context.get("acceptance_criteria", []),
                "constraints": routing_context.get("constraints", []),
                "expected_outcomes": routing_context.get("expected_outcomes", []),
                "parameters": routing_context.get("parameters", {}),
                "namespace_context": inferred_namespace,
                "agent_config": agent_config,
            }

            return {
                **cleanup_state,  # Clear old ticket first
                "messages": engine_result.get("messages", []),
                "next_node": routing_target,
                "current_plan": state.get("current_plan"),
                "structured_plan": state.get("structured_plan"),
                "execution_ticket": execution_ticket,  # <--- NEW (Overwrites cleanup if present)
                "scratchpad": {
                    **existing_scratchpad,
                    "last_supervisor_route": routing_target,
                    "route_reason": routing_reason,
                    "handoff_context": routing_context,
                    "visited_nodes": visited_nodes,
                },
                "workspace_context": state.get("workspace_context") or context.get("_structure_update")  # Persist cache
            }

        # Phase 5: Fallback - LLM did not call route_to
        # Check if it gave a direct text answer (should go to finish)
        new_messages = engine_result.get("messages", [])
        if new_messages:
            last_msg = new_messages[-1]
            if isinstance(last_msg, AIMessage) and not getattr(last_msg, "tool_calls", None):
                # Pure text response = consider task complete
                logger.info("[Supervisor] 🏁 Text response without routing - finishing.")
                return {
                    "messages": new_messages,
                    "next_node": "finish",
                    "current_plan": state.get("current_plan"),
                    **cleanup_state
                }

        # Ultimate fallback: default to Worker
        logger.warning("[Supervisor] ⚠️ No routing signal and no text response - defaulting to Worker")
        return {
            "messages": new_messages,
            "next_node": "worker",
            "current_plan": state.get("current_plan"),
            **cleanup_state
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

    async def _try_trimming(self, state: AgentState) -> dict[str, Any] | None:
        """
        Deterministic Sliding Window Trimming.
        Removes oldest messages when window exceeds threshold.
        Replaces legacy AI summarization (CompressorNode).
        """
        try:
            current_msgs = state.get("messages", [])
            max_msgs = 35  # Threshold to trigger trimming
            keep_last = 15  # Messages to keep at the end

            if len(current_msgs) <= max_msgs:
                return None

            logger.info(f"[Supervisor] ✂️ Trimming history: {len(current_msgs)} -> {keep_last} + 1")

            from langchain_core.messages import RemoveMessage, SystemMessage

            # 1. Identify System Prompt (always keep at index 0)
            has_sys = isinstance(current_msgs[0], SystemMessage)
            start_index = 1 if has_sys else 0
            end_index = len(current_msgs) - keep_last

            to_remove = current_msgs[start_index:end_index]

            delta = []
            for msg in to_remove:
                if msg.id:
                    delta.append(RemoveMessage(id=msg.id))

            if delta:
                # Return immediately to allow graph to process removals before next LLM call
                return {"messages": delta, "next_node": "supervisor"}

        except Exception as e:
            logger.error(f"[Supervisor] Trimming failed: {e}")

        return None

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> dict[str, Any]:
        """Build context for LLM planning."""
        # 1. Get Tools
        # Track 9: Progressive Disclosure
        # We NO LONGER inject `mcp_client_manager.get_tools()` into the Supervisor.
        # The Supervisor relies on `search_native_tools` and `use_mcp_server`
        # to find capabilities without blowing up the context window.
        core_tools = tool_manager.get_node_tools("supervisor", state)

        # 1.1 Context Extraction (Safe access)
        last_msg = get_last_human_message(messages)

        # In the new architecture, we provide a deterministic set of tools
        # plus search_native_tools for on-demand discovery.
        # RAG-based tool retrieval is deprecated.
        tool_dict = {t.name: t for t in core_tools}
        tools = list(tool_dict.values())

        # 2. Get Project Concepts
        project_concepts = ""
        try:
            if last_msg:
                results = await memory_manager.long_term.search_concepts(last_msg, project_id)
                if results:
                    found = "\n".join([f"- **{r.name}**: {r.description}" for r in results[:3]])
                if found and "No relevant concepts" not in found:
                    project_concepts = f"\nRelevant Project Concepts:\n{found}"

        except Exception as e:
            project_concepts = f"\n(Concept Search Failed: {e})"

        # 3. Project Orientation & Hydration
        from app.core.context import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        cwd = config.get("configurable", {}).get("working_directory")
        ctx.metadata["cwd"] = cwd
        ctx.metadata["project_concepts"] = project_concepts

        # User language preference will be fetched by prompt builder directly
        plugin_registry.hydrate_context(ctx)

        logger.info(f"[Supervisor] 📂 Context Hydrated: Concepts {len(project_concepts)} chars.")

        return {
            "tools": tools,
            "iteration_count": state.get("iteration_count", 0),
            "last_human_msg": last_msg,  # Pass for ambiguity check
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
