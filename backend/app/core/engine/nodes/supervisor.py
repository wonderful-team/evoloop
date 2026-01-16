"""
Supervisor Node - Refactored as Class

The Supervisor is the decision-making hub of the EvoLoop system.
It analyzes user input, routes to specialized nodes, and orchestrates the workflow.
"""
import logging
import os
import platform
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.engine import AgentEngine
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return None


SUPERVISOR_SYSTEM_TEMPLATE = """You are the Supervisor of an elite coding team.
    
    **MISSION**: Your goal is to PREPARE the workspace for specialized workers (Coder, Deep Researcher). You do not write code yourself; you Analyze, Plan, and Route.

    **WORKFLOW PHASES**:
    1. **Explore**: If uncertain, use `manage_file` to inspect the directory tree or read critical documents.

    **CRITICAL PROTOCOL**:
    1. **Context First**: 
       - If you are unsure about the file structure, call `manage_file_read_only(action='list_tree')` FIRST.
       - If user mentions a file/doc, call `manage_file_read_only(action='read')` IMMEDIATELY.

    2. **Explicit Planning (MANDATORY)**:
       - You MUST have a plan (`current_plan`) before delegating to Coder.
       
       **FAST TRACK PROTOCOL (For Simple Tasks OR Wiki)**:
       - IF the request is simple (e.g., "Fix typo") OR is about "Wiki/Documentation" generation, DO NOT explore or plan.
       - IMMEDIATE ACTION: Reply "Proceeding to specialized agent." (This stops the tool loop and enables routing).
       - DO NOT call `manage_file` or `create_plan`.
       
       **DEEP PLANNING (For Complex Tasks)**:
       - IF the request involves multiple files, architecture changes, or new features -> Route to `planner`.
       - IF the user wants to CHANGE/ADD requirements -> Route to `requirement_analyst` (DO NOT code yet).
       
    3. **STRICT DELEGATION PROTOCOL (MANAGER ROLE)**:
       - You are a **MANAGER**, not an Expert Coder.
       - **DO NOT WRITE APPLICATION CODE** (.php, .py, .ts, etc.) yourself.
       - **ALWAYS DELEGATE** implementation to the `coder` node.
       - **NO PLAN = NO CODE**: If `current_plan` is empty or "No plan yet", YOU MUST NOT route to `coder`. Route to `planner` or `requirement_analyst` instead.

    4. **Active Learning (Self-Evolution)**:
       - If user states a preference (e.g., "Use pytest"), call `save_preference`.

    5. **Language Protocol**:
       - User Language: {user_lang}
       - Communicate in this language, BUT **KEEP COMMAND SIGNALS IN ENGLISH**.
       
    **EXIT / HANDOFF STRATEGY**:
    - **To Coder**: When you have a solid, feasible plan -> Output EXACTLY: "Plan verified. Ready for Coder."
    - **To Researcher**: Output EXACTLY: "Need more research on X."
    - **Direct Reply**: For simple questions -> Output the answer text directly.

    **Dynamic HITL Protocol**:
    - Use `request_human_input` if ambiguous or risky. System will pause.

    **Think Before Action**:
    - **CHECK HISTORY**: Before calling ANY tool, check if you have just performed this action.
    - **AVOID REDUNDANCY**: If you have already read a file or searched a query and received a valid result, DO NOT repeat it.
    
    Current Plan: {current_plan}
    Project ID: {project_id}
    Iteration: {iteration_count}
    System Info: {system_info}
    
    Follow protocol: Explore -> Plan -> Handoff. Do not code directly.
    """


class RoutingDecision(BaseModel):
    """Decision on the next step in the workflow."""
    next_node: Literal[
        "planner", "coder", "deep_researcher", "documenter", "finish", "map_research",
        "requirement_analyst", "chat", "browser_executor", "computer_executor", "mobile_executor"
    ] = Field(description="The next worker node to route to. Default to 'finish' if done.")

    parallel_research_tasks: list[str] | None = Field(
        default=None,
        description="List of topics to research in parallel. REQUIRED if next_node is 'map_research'."
    )
    tool_profile: Literal["GENERAL", "DEVOPS", "RESEARCH"] | None = Field(
        default="GENERAL",
        description="The tool profile to activate for the Coder."
    )
    retrieval_query: str | None = Field(
        default=None,
        description="Optional keywords to retrieve specialized tools from database."
    )


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
        """Main entry point for the Supervisor node."""
        llm = LLMFactory.create_llm()
        project_id = state.get("project_id", 1)
        messages = list(state.get("messages", []))
        if not messages:
            logger.warning("[Supervisor] No messages found in state. Exiting.")
            return {"next_node": "finish"}

        # Emit initial status
        await self._emit_status(config, "Analyzing context...")

        # Phase 0: Context Compression
        compression_result = await self._try_compression(state)
        if compression_result:
            return compression_result

        # Phase 1: Fast Path (IntentClassifier + SkillMatcher)
        fast_result = await self._try_fast_path(state, config)
        if fast_result:
            return fast_result

        # Phase 2: Build Context
        context = await self._build_context(state, config, messages, project_id)

        # Phase 3: LLM Planning (via AgentEngine)
        engine_result = await self._run_planning(state, config, context, project_id)
        messages.extend(engine_result.get("messages", []))

        # Phase 4: Check for special conditions (HITL, research report)
        special_result = self._check_special_conditions(state, messages, engine_result)
        if special_result:
            return special_result

        # Phase 5: Make Routing Decision
        return await self._make_routing_decision(state, config, messages, context, engine_result)

    async def _emit_status(self, config: RunnableConfig, status: str):
        """Emit status update for UI responsiveness."""
        try:
            from app.core.monitoring.activity import activity_monitor
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            await activity_monitor.update_agent_state(
                thread_id=thread_id,
                mode="PLANNING",
                task_name="Supervisor Decision",
                task_status=status
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
        current_msgs = state.get("messages", [])
        last_human_msg = get_last_human_message(current_msgs)

        if not last_human_msg:
            return None

        # 1. Intent Classification
        try:
            from app.core.engine.intent_classifier import IntentClassifier
            fast_route = await IntentClassifier.classify(last_human_msg)
            if fast_route:
                logger.info(f"[Supervisor] ⚡ Fast-Track routing to '{fast_route}'")
                return {
                    "next_node": fast_route,
                    "messages": [],
                    "current_plan": state.get("current_plan"),
                }
        except Exception as e:
            logger.warning(f"IntentClassifier failed: {e}")

        # 2. Skill Matching
        if not state.get("skill_execution_attempted"):
            try:
                from app.core.learning.skill_executor import (
                    SkillExecutor,
                    skill_matcher,
                )
                from app.domain.tools.registry import get_supervisor_tools
                from app.infrastructure.mcp.client import mcp_client_manager

                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                match = await skill_matcher.match(last_human_msg, threshold=0.7, thread_id=thread_id)

                if match:
                    logger.info(f"🎯 Skill Match: '{match.skill_name}' ({match.confidence:.2f})")
                    core_tools = get_supervisor_tools()
                    mcp_tools = mcp_client_manager.get_tools()
                    tool_registry = {t.name: t for t in core_tools + mcp_tools}

                    executor = SkillExecutor(config)
                    success, result = await executor.execute_skill(
                        match.skill_id, match.extracted_params, tool_registry
                    )

                    content = f"✅ Executed skill '{match.skill_name}':\n{result}" if success else f"⚠️ Skill failed:\n{result}"
                    return {
                        "messages": [AIMessage(content=content)],
                        "next_node": "finish",
                        "skill_execution_attempted": True
                    }
            except Exception as e:
                logger.warning(f"Skill matching failed: {e}")

        return None

    async def _build_context(self, state: AgentState, config: RunnableConfig,
                             messages: list, project_id: int) -> dict[str, Any]:
        """Build context for LLM planning."""
        from app.core.tools.registry_utils import get_node_tools
        from app.domain.system.service import SystemConfigService
        from app.domain.tools.retrieval import tool_retriever
        from app.infrastructure.mcp.client import mcp_client_manager

        # 1. Get Tools
        core_tools = get_node_tools("supervisor")
        mcp_tools = mcp_client_manager.get_tools()
        await tool_retriever.index_tools(mcp_tools)

        # Build query context
        query_context = state.get("task_status", "General task")
        last_msg = messages[-1].content if messages and isinstance(messages[-1].content, str) else ""
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
            k_value = 5   # Simple Q&A needs fewer tools
        
        # Retrieve relevant tools
        retrieved_tools = await tool_retriever.retrieve(query_context, k=k_value)
        tool_dict = {t.name: t for t in core_tools + retrieved_tools}
        tools = list(tool_dict.values())

        # 2. Get Project Concepts
        project_concepts = ""
        try:
            from app.domain.memory.service import memory_service
            if last_msg:
                found = await memory_service.search_concepts(last_msg, project_id)
                if found and "No relevant concepts" not in found:
                    project_concepts = f"\nRelevant Project Concepts:\n{found}"
        except Exception as e:
            project_concepts = f"\n(Concept Search Failed: {e})"

        # 3. Get Project Structure
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
        project_structure = "Tree not available"
        try:
            from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
            generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
            project_structure = await generator.generate()
        except Exception as e:
            project_structure = f"Tree error: {e}"

        # 4. Build System Info
        user_lang = SystemConfigService.get_language_preference()
        sys_info = f"OS: {platform.system()} {platform.release()}, CWD: {cwd}\nLanguage: {user_lang}\n\nProject Structure:\n{project_structure[:5000]}{project_concepts}"

        logger.info(f"[Supervisor] 📂 Context: Tree {len(project_structure)} chars, Concepts {len(project_concepts)} chars")

        return {
            "tools": tools,
            "sys_info": sys_info,
            "user_lang": user_lang,
            "cwd": cwd,
            "current_plan": state.get("current_plan", "No plan yet."),
            "iteration_count": state.get("iteration_count", 0)
        }

    async def _run_planning(self, state: AgentState, config: RunnableConfig,
                           context: dict[str, Any], project_id: int) -> dict[str, Any]:
        """Run LLM planning via AgentEngine."""
        dynamic_prompt = SUPERVISOR_SYSTEM_TEMPLATE.format(
            project_id=project_id,
            current_plan=context["current_plan"],
            iteration_count=context["iteration_count"],
            system_info=context["sys_info"],
            user_lang=context["user_lang"]
        )

        return await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=dynamic_prompt,
            tools=context["tools"],
            max_steps=10,
            name="Supervisor"
        )

    def _check_special_conditions(self, state: AgentState, messages: list,
                                  engine_result: dict[str, Any]) -> dict[str, Any] | None:
        """Check for special conditions that require immediate return."""
        new_messages = engine_result.get("messages", [])

        # Check for Deep Research Report
        if messages and isinstance(messages[-1], AIMessage):
            content = messages[-1].content
            if any(x in content for x in ["Full Research Report", "Detailed Conclusion", "# Final Conclusion"]):
                logger.info("Supervisor detected Research Report. Routing to FINISH.")
                return {
                    "next_node": "finish",
                    "messages": new_messages,
                    "current_plan": state.get("current_plan"),
                    "parallel_research_tasks": []
                }

        # Check for HITL State
        hitl = state.get("hitl_state")
        if hitl:
            last_msg = messages[-1] if messages else None
            if isinstance(last_msg, HumanMessage):
                resume_node = hitl.get("resume_node", "supervisor")
                logger.info(f"HITL Active + Human Input -> Resuming '{resume_node}'.")
                return {
                    "next_node": resume_node,
                    "messages": new_messages,
                    "current_plan": state.get("current_plan"),
                }
            else:
                logger.info("HITL Active + No Human Input -> Waiting (finish).")
                return {
                    "next_node": "finish",
                    "messages": new_messages,
                    "current_plan": state.get("current_plan"),
                }

        # Check for Human Input Request
        if messages and isinstance(messages[-1], ToolMessage):
            if messages[-1].name in ["request_human_input", "request_approval"]:
                logger.info("Human Input requested. Creating interrupt point (finish).")
                return {
                    "next_node": "finish",
                    "messages": new_messages,
                    "current_plan": state.get("current_plan"),
                }

        return None

    async def _make_routing_decision(self, state: AgentState, config: RunnableConfig,
                                     messages: list, context: dict[str, Any],
                                     engine_result: dict[str, Any]) -> dict[str, Any]:
        """Make final routing decision via LLM."""
        llm = LLMFactory.create_llm()
        new_messages = engine_result.get("messages", [])

        parser = JsonOutputParser(pydantic_object=RoutingDecision)
        format_instructions = parser.get_format_instructions()

        from app.core.prompts.supervisor_builder import SupervisorPromptBuilder
        routing_prompt = SupervisorPromptBuilder.build_routing_prompt(format_instructions)

        chain = routing_prompt.partial(
            system_info=context["sys_info"],
            format_instructions=format_instructions
        ) | llm | parser

        # Execute routing decision (hide from user)
        routing_config = config.copy() if config else {}
        routing_config["callbacks"] = []

        decision = None
        next_node = "deep_researcher"
        try:
            raw = await chain.ainvoke(state, config=routing_config)
            decision = RoutingDecision(**raw)
            next_node = decision.next_node
        except InterruptedError:
            raise
        except Exception as e:
            logger.warning(f"Routing decision failed: {e}")

        # Handle map_research fallback
        parallel_tasks = []
        if decision:
            if next_node == "map_research" and not decision.parallel_research_tasks:
                next_node = "deep_researcher"
            parallel_tasks = decision.parallel_research_tasks or []

        profile = decision.tool_profile if decision else "GENERAL"
        query = decision.retrieval_query if decision else None

        logger.info(f"[Supervisor] 🚦 Routing: {next_node} (Profile: {profile})")

        return {
            "next_node": next_node,
            "messages": new_messages,
            "current_plan": state.get("current_plan"),
            "structured_plan": state.get("structured_plan"),
            "parallel_research_tasks": parallel_tasks,
            "active_tool_profile": profile,
            "tool_retrieval_query": query,
            "scratchpad": {"last_supervisor_route": next_node}
        }


# Create singleton instance for graph registration
_supervisor_instance = SupervisorNode()


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Supervisor node function wrapper for graph registration."""
    return await _supervisor_instance(state, config)
