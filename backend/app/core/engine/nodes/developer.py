import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine, repair_message_history
from app.core.engine.message_utils import get_message_text
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.prompts.developer_builder import DeveloperPromptBuilder
from app.core.tools.registry_utils import get_node_tools
from app.domain.tools.vector_store import pg_tool_retriever
from app.infrastructure.mcp.client import mcp_client_manager
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class DeveloperNode:
    """
    Developer Node (v3.0 Functional Architecture)
    
    Consolidates Coder + Tester + Lite Planner.
    Capabilities:
    1. Plan (Optional): Break down complex tasks.
    2. Code: Write/Edit files.
    3. Verify: Run tests/commands to verify changes.
    4. Self-Correct: Inner loop to fix issues without graph transitions.
    """

    async def __call__(
        self, state: AgentState, config: RunnableConfig, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Entry point for Developer Node."""
        
        # 1. Context Handling
        mw_context = context or {}
        project_id = config.get("metadata", {}).get("project_id", 1)
        
        # 2. Tool Preparation (Static + Dynamic)
        tools = await self._get_tools(state)
        
        # 3. Generate Project Structure (Cached)
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
        project_context = state.get("project_context") or {}
        if project_context.get("structure"):
            project_structure = project_context["structure"]
            logger.info("[Developer] 🌳 Cache Hit: Using cached project structure")
        else:
            project_structure = await self._generate_project_tree(cwd)
        
        # 4. Prompt Construction
        prompt_builder = DeveloperPromptBuilder(
            state=state,
            context={
                "explicit_context": state.get("context", ""),
                "project_structure": project_structure[:5000],
            },
            project_id=project_id,
        )
        
        system_msg = prompt_builder.build(config)
        
        # 5. Attention Guidance Hydration (Focus Files)
        scratchpad = state.get("scratchpad", {})
        handoff_context = scratchpad.get("handoff_context", {})
        
        hydration_prompt = await self._hydrate_context(handoff_context, cwd)
        if hydration_prompt:
            system_msg += f"\n\n{hydration_prompt}"
            
        # 6. Instruction Injection & Worker Isolation (v3.1 Stateless)
        execution_ticket = state.get("execution_ticket")
        route_reason = scratchpad.get("route_reason")
        original_messages = list(state.get("messages", []))
        
        if execution_ticket:
            logger.info("[Developer] 🎫 Ticket Match - Enabling Stateless Mode Isolation")
            # In stateless mode, we only care about the System Prompt + Ticket + Latest instruction
            # We don't need the whole multi-hop history which might confuse the worker
            
            # Construct a concentrated instruction
            criteria = "\n".join([f"- {c}" for c in execution_ticket.get("acceptance_criteria", [])])
            constraints = "\n".join([f"- {c}" for c in execution_ticket.get("constraints", []) or []])
            
            isolated_instruction = f"""### MISSION TICKET
**Goal**: {route_reason or "Assigned Task"}
**Type**: {execution_ticket.get('ticket_type', 'task')}
**Priority**: {execution_ticket.get('priority', 'normal')}

**Acceptance Criteria**:
{criteria}

**Constraints**:
{constraints}

Please execute this mission now. Use your tools to verify success against the criteria.
"""
            # Prune messages: Only keep the concentrated instruction
            messages = [HumanMessage(content=isolated_instruction)]
        else:
            # Fallback to standard history-based flow if no ticket
            messages = original_messages
            if route_reason:
                logger.info(f"Injecting Supervisor Instruction: {route_reason}")
                messages.append(HumanMessage(content=f"SUPERVISOR INSTRUCTION: {route_reason}\n\nExecute this task. If you need to verify, run tests."))

        # 7. Execution (Inner Loop handled by AgentEngine)
        # We increase max_steps because the Developer does more things (Edit -> Run -> Fix)
        logger.info("Developer delegating to AgentEngine")
        
        engine_result = await AgentEngine.run_node(
            state={**state, "messages": messages},
            config=config,
            system_prompt=system_msg,
            tools=tools,
            name="Developer",
            max_steps=20, # Higher limit for inner loop
        )
        
        return self._post_process_result(state, engine_result)
    
    def _post_process_result(self, state: AgentState, result: dict) -> dict:
        """Handle cache invalidation based on tool usage."""
        tool_history = result.get("tool_history", [])
        
        # Check for file modification tools
        write_tools = ["write_file", "edit_file", "manage_file"]
        has_changes = any(
            any(wt in t_sig for wt in write_tools) 
            for t_sig in tool_history
        )
        
        if has_changes:
            logger.info("[Developer] ♻️ File changes detected - Invalidating Project Structure Cache")
            if "scratchpad" not in result:
                result["scratchpad"] = {}
            result["project_context"] = {"structure": None, "structure_updated_at": 0.0}
            
        # [NEW] Phase 8.2: Structured Test Result Capture
        # We look for test/run signals in the history
        test_summary = {"total": 0, "passed": 0, "failed": 0, "status": "unknown"}
        for t_sig in tool_history:
            # Simple heuristic: look for 'pytest' or 'test' in the tool signature/content
            if "test" in t_sig.lower() or "run_command" in t_sig.lower():
                # We assume the last test tool call is the most relevant
                # In a real scenario, we might parse the ToolMessage content
                # For now, we flag it for Supervisor observation
                test_summary["status"] = "verified" # Marker that testing was attempted
        
        result["structured_test_results"] = test_summary
            
        return result

    async def _get_tools(self, state: AgentState) -> list[Any]:
        """Combine Developer tools + Dynamic tools."""
        # A. Static Core Tools (FileSystem, Shell, etc.)
        tools = get_node_tools("developer") 
        
        # Deduplicate and start combined map
        combined_map = {t.name: t for t in tools}

        # B. Dynamic (RAG Tools)
        retrieval_query = state.get("tool_retrieval_query")
        if retrieval_query:
            records = await pg_tool_retriever.search_tools(retrieval_query, k=5)
            all_mcp = mcp_client_manager.get_tools()
            mcp_map = {t.name: t for t in all_mcp}

            for rec in records:
                if rec["name"] in mcp_map:
                    combined_map[rec["name"]] = mcp_map[rec["name"]]
        
        return list(combined_map.values())

    async def _generate_project_tree(self, cwd: str) -> str:
        try:
            from app.core.context import AnnotatedTreeGenerator
            generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
            return await generator.generate()
        except Exception as e:
            return f"Tree error: {e}"

    async def _hydrate_context(self, context: dict, cwd: str) -> str:
        """Hydrate focus files into content."""
        if isinstance(context, str):
            try:
                import json
                context = json.loads(context)
            except Exception:
                context = {}

        output = []
        focus_paths = context.get("focus_paths", [])

        if not focus_paths:
            return ""

        output.append("### SUPERVISOR HANDOFF CONTEXT (ATTENTION GUIDANCE)")
        output.append(f"The Supervisor has identified {len(focus_paths)} focus files for you. I have pre-read them:")

        for rel_path in focus_paths:
            try:
                full_path = os.path.join(cwd, rel_path)
                if not os.path.exists(full_path):
                    output.append(f"- [MISSING] {rel_path}")
                    continue

                size = os.path.getsize(full_path)
                if size > 30_000: # 30KB limit
                    output.append(f"- [SKIPPED] {rel_path} (Too large {size}b)")
                    continue

                with open(full_path, encoding="utf-8") as f:
                    content = f.read()

                output.append(f"\n--- FILE: {rel_path} ---\n{content}\n--- END OF FILE ---\n")

            except Exception as e:
                output.append(f"- [ERROR] {rel_path}: {e}")

        return "\n".join(output) + "\n"

# Singleton
developer_node = DeveloperNode()
