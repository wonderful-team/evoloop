"""
Supervisor Node - ReAct Architecture

The Supervisor is the decision-making hub of the EvoLoop system.
It analyzes user input, routes to specialized nodes via the route_to tool.
"""
import json
import logging
import os
import platform
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import or_, select

from app.core.engine import AgentEngine
from app.core.engine.message_utils import get_message_text
from app.core.engine.state import AgentState
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import (
    TodoItem,
    TodoPriority,
    TodoStatus,
)

logger = logging.getLogger(__name__)


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

        # Phase 1: Fast Path (IntentClassifier + SkillMatcher)
        fast_result = await self._try_fast_path(state, config)
        if fast_result:
            return fast_result

        # Phase 2: Build Context
        context = await self._build_context(state, config, messages, project_id)

        # Phase 3: Single ReAct Loop (Routing tools now provided via agent_main.yaml)
        tools = context["tools"]

        # Use Builder for unified prompt construction
        from app.core.engine.prompts import SupervisorPromptBuilder

        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            active_plan_context=context["active_plan_context"],
            iteration_count=context["iteration_count"],
            sys_info=context["sys_info"],
            context=context,
        )
        dynamic_prompt = prompt_builder.build(config)

        engine_result = await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=dynamic_prompt,
            tools=tools,
            max_steps=15,  # Increased since routing is now part of the loop
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

            # Phase 21: Extract Context Handoff
            routing_reason = engine_result.get("_routing_reason", "")
            routing_context = engine_result.get("_routing_context", {})
            
            # Defensive check: ensure routing_context is a dict
            if isinstance(routing_context, str):
                try:
                    routing_context = json.loads(routing_context)
                    if isinstance(routing_context, str): # Handle double encoding
                        routing_context = json.loads(routing_context)
                except Exception:
                    routing_context = {}

            if not isinstance(routing_context, dict):
                routing_context = {}

            # [NEW] Phase 8/9: Universal Blackboard Ticket Population
            execution_ticket = None
            specialists = ["developer", "deep_researcher", "documenter"]
            
            if routing_target in specialists:
                execution_ticket = {
                    "ticket_type": routing_context.get("ticket_type", "task"),
                    "priority": routing_context.get("priority", "normal"),
                    "focus_paths": routing_context.get("focus_paths", []),
                    "topic": routing_context.get("topic") or routing_context.get("query"),
                    "acceptance_criteria": routing_context.get("acceptance_criteria", []),
                    "constraints": routing_context.get("constraints", []),
                    "expected_outcomes": routing_context.get("expected_outcomes", []),
                    "parameters": routing_context.get("parameters", {}),
                }
            elif routing_target == "dynamic_specialist":
                 # [NEW] v4.0 Dynamic Agent Ticket Population
                 agent_config = routing_context.get("agent_config")
                 if agent_config:
                     execution_ticket = {
                        "ticket_type": routing_context.get("ticket_type", "adhoc_task"),
                        "priority": "normal",
                        "topic": "Dynamic Task",
                        "acceptance_criteria": routing_context.get("acceptance_criteria", []),
                        "agent_config": agent_config, # The Blueprint
                        # Dynamic specialist doesn't usually use focus_paths like Developer, 
                        # but we can pass them if tools support it.
                        "parameters": routing_context.get("parameters", {}),
                        # Required fields (nullable in TypeDict but good to have keys)
                        "focus_paths": None,
                        "constraints": None,
                        "expected_outcomes": None
                    }

            return {
                **cleanup_state, # Clear old ticket first
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
                "project_context": state.get("project_context") or context.get("_structure_update") # Persist cache
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

        # Ultimate fallback: default to deep_researcher
        logger.warning("[Supervisor] ⚠️ No routing signal and no text response - defaulting to deep_researcher")
        return {
            "messages": new_messages,
            "next_node": "deep_researcher",
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
            max_msgs = 35 # Threshold to trigger trimming
            keep_last = 15 # Messages to keep at the end

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

    async def _try_fast_path(self, state: AgentState, config: RunnableConfig) -> dict[str, Any] | None:
        """Try fast-path routing via IntentClassifier and SkillMatcher."""
        # Prevent Fast Path Loop: Only fast-track if the VERY LAST message was from Human.
        # If the last message was AI/Tool, we must let the Supervisor LLM decide the next step (Slow Path).
        current_msgs = state.get("messages", [])
        if not current_msgs or not isinstance(current_msgs[-1], HumanMessage):
            return None
        last_human_msg = get_last_human_message(current_msgs)

        if not last_human_msg:
            return None

        # Skill Matching (Knowledge-Only)
        # Skills are NOT tools. When a skill matches, we only log it.
        # The actual skill knowledge injection happens in downstream Worker Nodes
        # (DeveloperNode, DynamicSpecialistNode) via SkillRetriever + Prompt builders.
        if not state.get("skill_execution_attempted"):
            try:
                from app.core.learning.discovery import skill_discovery

                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                match = await skill_discovery.match(last_human_msg, threshold=0.7, thread_id=thread_id)

                if match:
                    logger.info(
                        f"🎯 Skill Knowledge Match: '{match.skill_name}' "
                        f"(confidence: {match.confidence:.2f}) - "
                        f"will be injected as context by downstream Worker Node"
                    )
                    # Do NOT call skill as a tool. Fall through to slow path
                    # so Supervisor LLM can route to the appropriate Worker Node.
            except Exception:
                pass

        return None

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> dict[str, Any]:
        """Build context for LLM planning."""
        from app.core.tools.registry import get_node_tools
        from app.infrastructure.config.service import SystemConfigService
        from app.infrastructure.mcp.client import mcp_client_manager

        # 1. Get Tools
        core_tools = get_node_tools("supervisor")
        mcp_tools = mcp_client_manager.get_tools()
        
        # 1.1 Context Extraction (Safe access)
        last_msg = get_last_human_message(messages)

        # In the new architecture, we provide a deterministic set of tools 
        # plus search_native_tools for on-demand discovery.
        # RAG-based tool retrieval is deprecated.
        all_tools_list = core_tools + mcp_tools
        tool_dict = {t.name: t for t in all_tools_list}
        tools = list(tool_dict.values())

        # 2. Get Project Concepts
        project_concepts = ""
        try:
            from app.core.memory import memory_manager

            if last_msg:
                results = await memory_manager.long_term.search_concepts(last_msg, project_id)
                if results:
                    found = "\n".join([f"- **{r.name}**: {r.description}" for r in results[:3]])
                if found and "No relevant concepts" not in found:
                    project_concepts = f"\nRelevant Project Concepts:\n{found}"
        except Exception as e:
            project_concepts = f"\n(Concept Search Failed: {e})"

        # 3. Project Orientation (Minimal)
        cwd = config.get("configurable", {}).get("working_directory")
        if cwd:
            project_structure_stub = f"CWD: {cwd}\n(Use 'list_project_structure' to examine files if needed)"
        else:
            project_structure_stub = "CWD: None (No Local Workspace Attached)\n(You are operating in a universal context. Do NOT assume local files exist unless specified by the user.)"

        # 4. Build System Info
        user_lang = SystemConfigService.get_language_preference()

        # 5. Inject Cognitive Todo Context
        todo_context = ""
        try:
            async with session_scope() as session:
                # Query: Pending AND (High Priority OR Overdue) AND (Global OR Current Project)
                from datetime import datetime
                query = select(TodoItem).where(
                    TodoItem.status == TodoStatus.PENDING,
                    or_(
                        TodoItem.priority == TodoPriority.HIGH,
                        TodoItem.due_date < datetime.now()
                    )
                ).limit(5)  # Limit to 5 max to avoid context bloat

                # If project isolation is strict, add project_id check
                # query = query.where(or_(TodoItem.project_id == project_id, TodoItem.project_id == None))

                result = await session.execute(query)
                urgent_todos = result.scalars().all()

                if urgent_todos:
                    todo_list = "\n".join([f"- [URGENT] {t.title} (Due: {t.due_date})" for t in urgent_todos])
                    todo_context = f"\n\n🔥 URGENT TASKS (Cognitive Injection):\n{todo_list}\n(You can use 'manage_todo' to check details or mark as done)"
        except Exception as e:
            logger.warning(f"Failed to load todo context: {e}")

        # 6. Inject Active Plan Context (DB)
        active_plan_context = i18n.get("prompts.supervisor.no_active_plan")
        try:
            async with session_scope() as session:
                from app.models.planning import Plan, PlanStep
                thread_id = config.get("configurable", {}).get("thread_id")

                if thread_id:
                    # Find Plan
                    stmt = select(Plan).where(Plan.thread_id == thread_id, Plan.status == "active")
                    res = await session.execute(stmt)
                    db_plan = res.scalars().first()

                    if db_plan:
                        # Find Steps
                        stmt_steps = select(PlanStep).where(PlanStep.plan_id == db_plan.id).order_by(PlanStep.order)
                        res_steps = await session.execute(stmt_steps)
                        steps = res_steps.scalars().all()

                        # Format
                        steps_str = ""
                        active_step_found = False
                        for s in steps:
                            marker = "[ ]"
                            if s.status == "completed":
                                marker = "[x]"
                            elif s.status == "in_progress":
                                marker = "[>] (CURRENT)"
                            elif s.status == "failed":
                                marker = "[!]"

                            steps_str += f"\n{marker} {s.title}"
                            if s.status == "in_progress":
                                active_step_found = True

                        active_plan_context = f"PLAN: {db_plan.title}\nSTEPS:{steps_str}"
                        if active_step_found:
                            active_plan_context += "\n\n-> FOCUS: Execute the [>] CURRENT step."
                        else:
                            active_plan_context += "\n\n-> ACTION: Mark the next step as in_progress."
        except Exception as e:
            logger.warning(f"Failed to load active plan: {e}")

        # 7. ATTENTION GUIDANCE PROTOCOL (Phase 21)
        protocol_prompt = """
### ATTENTION GUIDANCE PROTOCOL (CRITICAL)
You act as the **NAVIGATOR** for the Coder/Tester. They rely on your ticket for context.
When you call `route_to(target='developer', ...)`:
1. **Consult the File Tree** above.
2. Identify 1-3 files that are CRITICAL for the task.
3. Define how to verify success (Acceptance Criteria).
4. **Construct the Ticket**:
   `route_to(target="developer", reason="Implement login", context={
       "ticket_type": "feature",
       "priority": "normal",
       "focus_paths": ["src/main.py"],
       "acceptance_criteria": ["Login endpoint returns 200", "Token is returned"]
   })`

**DO NOT** make the Coder guess. Point to the file strategies.
"""

        sys_info = f"OS: {platform.system()} {platform.release()}, CWD: {cwd}\nLanguage: {user_lang}\n\nProject Architecture:\n{project_structure_stub}{project_concepts}{todo_context}\n{protocol_prompt}"

        logger.info(f"[Supervisor] 📂 Context: Concepts {len(project_concepts)} chars, Todos {len(todo_context)} chars")

        return {
            "tools": tools,
            "sys_info": sys_info,
            "user_lang": user_lang,
            "cwd": cwd,
            "active_plan_context": active_plan_context,
            "iteration_count": state.get("iteration_count", 0),
            "last_human_msg": last_msg,  # Pass for ambiguity check
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
