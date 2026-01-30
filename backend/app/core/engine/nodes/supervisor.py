"""
Supervisor Node - ReAct Architecture

The Supervisor is the decision-making hub of the EvoLoop system.
It analyzes user input, routes to specialized nodes via the route_to tool.
"""

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

        # Emit initial status
        await self._emit_status(config, i18n.get("prompts.supervisor.status_analyzing"))

        # Phase 0: Context Compression (optional optimization)
        compression_result = await self._try_compression(state)
        if compression_result:
            return compression_result

        # Phase 1: Fast Path (IntentClassifier + SkillMatcher)
        fast_result = await self._try_fast_path(state, config)
        if fast_result:
            return fast_result

        # Phase 2: Build Context
        context = await self._build_context(state, config, messages, project_id)

        # Phase 3: Single ReAct Loop with route_to tool (Core Change)
        # Import route_to tool and add to tools list
        from app.domain.tools.routing import route_to

        tools = context["tools"] + [route_to]

        # Use Builder for unified prompt construction
        from app.core.prompts import SupervisorPromptBuilder

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
            routing_context = engine_result.get("_routing_context", {})  # <--- NEW: Capture context

            return {
                "messages": engine_result.get("messages", []),
                "next_node": routing_target,
                "current_plan": state.get("current_plan"),
                "structured_plan": state.get("structured_plan"),  # Propagate plan for prompt builder
                "scratchpad": {
                    **existing_scratchpad,
                    "last_supervisor_route": routing_target,
                    "route_reason": routing_reason,
                    "handoff_context": routing_context,  # <--- NEW: Persist context
                    "visited_nodes": visited_nodes,
                },
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
                }

        # Ultimate fallback: default to deep_researcher
        logger.warning("[Supervisor] ⚠️ No routing signal and no text response - defaulting to deep_researcher")
        return {
            "messages": new_messages,
            "next_node": "deep_researcher",
            "current_plan": state.get("current_plan"),
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

    async def _try_compression(self, state: AgentState) -> dict[str, Any] | None:
        """Try to compress history if needed."""
        try:
            from app.core.engine.nodes.compressor import compress_history_delta

            current_msgs = state.get("messages", [])
            delta = await compress_history_delta(current_msgs)
            if delta:
                return {"messages": delta, "next_node": "supervisor"}
        except Exception:
            pass
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

        # 1. Intent Classification
        try:
            from app.core.engine.intent_classifier import IntentClassifier

            fast_route = await IntentClassifier.classify(last_human_msg)
            if fast_route:
                logger.info(f"[Supervisor] ⚡ Fast-Track routing to '{fast_route}'")

                # [FIX] Phase 21: Auto-Populate Handoff Context for Fast Path
                # Specialized Logic used to map User Message -> Node Context
                handoff_context = {}
                scratchpad_update = {}

                if fast_route == "deep_researcher":
                    # Assume user message is the research topic
                    handoff_context = {"topic": last_human_msg}
                elif fast_route == "planner":
                    # Assume user message is the updated instruction
                    handoff_context = {"instruction": last_human_msg}

                if handoff_context:
                    scratchpad_update = {
                        "handoff_context": handoff_context,
                        "route_reason": "Fast-Track Intent",
                    }

                return {
                    "next_node": fast_route,
                    "messages": [],
                    "current_plan": state.get("current_plan"),
                    "scratchpad": scratchpad_update,  # Inject context
                }
        except Exception as e:
            logger.warning(f"IntentClassifier failed: {e}")

        # 2. Skill Matching
        if not state.get("skill_execution_attempted"):
            try:
                # Dynamic import for runtime matching
                from app.core.learning.skill_executor import skill_matcher

                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                match = await skill_matcher.match(last_human_msg, threshold=0.7, thread_id=thread_id)

                if match:
                    logger.info(f"🎯 Skill Match: '{match.skill_name}' ({match.confidence:.2f})")
                    return {
                        "next_node": "supervisor",  # Re-route to self to execute skill tool
                        # We return messages with ToolCall so the next step executes it
                        "messages": [AIMessage(content="", tool_calls=[{
                            "name": match.skill_name,
                            "args": match.parameters,
                            "id": "skill_call_" + match.skill_name
                        }])],
                        "skill_execution_attempted": True  # Mark as attempted to prevent loop
                    }
            except Exception:
                pass

        return None

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> dict[str, Any]:
        """Build context for LLM planning."""
        from app.core.tools.registry_utils import get_node_tools
        from app.core.system import SystemConfigService
        from app.domain.tools.retrieval import tool_retriever
        from app.infrastructure.mcp.client import mcp_client_manager

        # 1. Get Tools
        core_tools = get_node_tools("supervisor")
        mcp_tools = mcp_client_manager.get_tools()
        await tool_retriever.index_tools(mcp_tools)

        # Build query context
        query_context = state.get("task_status", "General task")
        last_msg = get_message_text(messages[-1]) if messages else ""
        query_context += f" {last_msg}"

        # Dynamic k value based on task complexity
        # Simple Q&A: fewer tools, Complex tasks: more tools
        complexity_indicators = ["implement", "build", "create", "refactor", "design", "architect"]
        simple_indicators = ["what", "how", "why", "explain", "?"]

        k_value = 10  # Default
        last_msg_lower = last_msg.lower()
        if any(ind in last_msg_lower for ind in complexity_indicators):
            k_value = 20  # Complex tasks need more tools
        elif any(ind in last_msg_lower for ind in simple_indicators) and len(last_msg) < 100:
            k_value = 5  # Simple Q&A needs fewer tools

        # Retrieve relevant tools
        retrieved_tools = await tool_retriever.retrieve(query_context, k=k_value)
        tool_dict = {t.name: t for t in core_tools + retrieved_tools}
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

        # 3. Get Project Structure
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
        project_structure = "Tree not available"
        try:
            from app.core.context import AnnotatedTreeGenerator
            generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
            project_structure = await generator.generate()
        except Exception as e:
            project_structure = f"Tree error: {e}"

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
You act as the **SCOUT** for the Coder/Tester. They are blind until you guide them.
When you call `route_to(target='coder', ...)` or `route_to(target='tester', ...)`:
1. **Consult the File Tree** above.
2. Identify 1-3 files that are CRITICAL for the task.
3. Pass them in the `context` argument: `context={"focus_paths": ["src/main.py", "tests/test_main.py"]}`.

**DO NOT** make the Coder guess where the code is. Point to it.
"""

        sys_info = f"OS: {platform.system()} {platform.release()}, CWD: {cwd}\nLanguage: {user_lang}\n\nProject Structure:\n{project_structure[:5000]}{project_concepts}{todo_context}\n{protocol_prompt}"

        logger.info(f"[Supervisor] 📂 Context: Tree {len(project_structure)} chars, Concepts {len(project_concepts)} chars, Todos {len(todo_context)} chars")

        return {
            "tools": tools,
            "sys_info": sys_info,
            "user_lang": user_lang,
            "cwd": cwd,
            "current_plan": state.get("current_plan", "No plan yet."),
            "active_plan_context": active_plan_context,
            "iteration_count": state.get("iteration_count", 0),
            "last_human_msg": last_msg,  # Pass for ambiguity check
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
