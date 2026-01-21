import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine
from app.core.engine.message_utils import get_message_text
from app.core.engine.state import AgentState
from app.core.prompts.coder_builder import CoderPromptBuilder
from app.core.tools.registry_utils import get_node_tools
from app.domain.tools.vector_store import pg_tool_retriever
from app.infrastructure.mcp.client import mcp_client_manager

logger = logging.getLogger(__name__)


class CoderNode:
    """
    Coder Node:
    1. Reads plan.
    2. Writes code using MCP tools.
    """

    async def __call__(
        self, state: AgentState, config: RunnableConfig, context: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Entry point for Coder Node."""

        # 1. Context Handling (Supports both Middleware and State)
        # We try to look for injected 'context' first (from Middleware), then fallback to State.
        # But effectively, we should move towards State-only or a clean Context Service.
        # For now, we extract specific keys manually.

        # Merge Middleware Context + State Context
        mw_context = context or {}

        plan = mw_context.get("current_plan") or state.get("current_plan", "")
        prefs = mw_context.get("user_preferences") or state.get("user_preferences", "None")
        concepts = mw_context.get("memory") or state.get("project_concepts", "None")  # Mapped to project_concepts in tasks.py

        project_id = config.get("metadata", {}).get("project_id", 1)

        # 2. Tool Preparation
        tools = await self._get_tools(state)

        # 2a. Generate Project Structure (Cure Blindness)
        cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
        project_structure = "Tree not available"
        try:
            from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
            generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
            project_structure = await generator.generate()
        except Exception as e:
            project_structure = f"Tree error: {e}"

        # 3. Prompt Construction
        prompt_builder = CoderPromptBuilder(
            plan=plan,
            context={
                "user_preferences": prefs,
                "project_concepts": concepts,
                "explicit_context": state.get("context", ""),
            },
            project_id=project_id,
            project_structure=project_structure[:5000],  # Inject Tree
        )

        system_msg = prompt_builder.build(config)

        # 4a. ATTENTION GUIDANCE HYDRATION (Phase 21)
        # Check if Supervisor pointed to specific files
        scratchpad = state.get("scratchpad", {})
        handoff_context = scratchpad.get("handoff_context", {})

        hydration_prompt = await self._hydrate_context(handoff_context, cwd)
        if hydration_prompt:
            system_msg += f"\n\n{hydration_prompt}"

        # 4b. FIX MODE Injection (QA Feedback)
        last_msg_content = ""
        messages = list(state.get("messages", []))  # Copy messages list
        if messages:
            last_msg_content = get_message_text(messages[-1])

        if "TEST PHASE: FAIL" in last_msg_content:
            system_msg += self._build_fix_mode_prompt(last_msg_content)

        # 5. INSTRUCTION INJECTION (Cure Deafness)
        # Extract specific instruction from Supervisor (via scratchpad)
        scratchpad = state.get("scratchpad", {})
        route_reason = scratchpad.get("route_reason")

        # Inject as a pseudo-HumanMessage at the end of history
        # This overrides previous context and focuses the model on the IMMEDIATE task.
        if route_reason:
            logger.info(f"Injecting Supervisor Instruction: {route_reason}")
            messages.append(HumanMessage(content=f"SUPERVISOR INSTRUCTION: {route_reason}\n\nExecute this specific instruction now."))

        # 6. Execution
        logger.info("Coder delegating to AgentEngine")

        return await AgentEngine.run_node(
            state={**state, "messages": messages},  # Pass modified messages
            config=config,
            system_prompt=system_msg,
            tools=tools,
            name="Coder",
        )

    async def _get_tools(self, state: AgentState) -> list[Any]:
        """Resolve generic and dynamic tools."""
        # A. Static
        core_tools = get_node_tools("coder")

        # B. Dynamic (RAG Tools)
        retrieval_query = state.get("tool_retrieval_query")
        dynamic_tools = []

        if retrieval_query:
            records = await pg_tool_retriever.search_tools(retrieval_query, k=5)
            all_mcp = mcp_client_manager.get_tools()
            mcp_map = {t.name: t for t in all_mcp}

            for rec in records:
                if rec["name"] in mcp_map:
                    dynamic_tools.append(mcp_map[rec["name"]])

        # Combine
        combined = {t.name: t for t in core_tools + dynamic_tools}
        return list(combined.values())

    def _build_fix_mode_prompt(self, feedback: str) -> str:
        return f"""

        !!! CRITICAL: FIX MODE ACTIVATED !!!
        The previous tests FAILED. You are now in FIX MODE.

        FEEDBACK FROM QA:
        {feedback}

        PROTOCOL:
        1. Read the failing file and the test file.
        2. Apply the 'FIX SUGGESTION' provided above if it makes sense.
        3. Verify the fix by running the test.
        """

    async def _hydrate_context(self, context: dict, cwd: str) -> str:
        """
        Hydrate context pointers into actual content.
        Protocol: Attention Guidance (Phase 21).
        """
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
                # Sanitize path
                full_path = os.path.join(cwd, rel_path)
                if not os.path.exists(full_path):
                    output.append(f"- [MISSING] {rel_path} (Supervisor pointed to non-existent file)")
                    continue

                # Check size
                size = os.path.getsize(full_path)
                if size > 20_000:  # 20KB limit for auto-read
                    output.append(f"- [SKIPPED] {rel_path} (Too large {size}b - Read manually if needed)")
                    continue

                # Read content
                with open(full_path, encoding="utf-8") as f:
                    content = f.read()

                output.append(f"\n--- FILE: {rel_path} ---\n{content}\n--- END OF FILE ---\n")

            except Exception as e:
                output.append(f"- [ERROR] {rel_path}: {e}")

        return "\n".join(output) + "\n"


# Instance for Graph
coder_node = CoderNode()
