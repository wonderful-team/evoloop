import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine
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

    async def __call__(self, state: AgentState, config: RunnableConfig, context: dict[str, Any] = None) -> dict[str, Any]:
        """Entry point for Coder Node."""

        # 1. Context Handling (Supports both Middleware and State)
        # We try to look for injected 'context' first (from Middleware), then fallback to State.
        # But effectively, we should move towards State-only or a clean Context Service.
        # For now, we extract specific keys manually.

        # Merge Middleware Context + State Context
        mw_context = context or {}

        plan = mw_context.get("current_plan") or state.get("current_plan", "")
        prefs = mw_context.get("user_preferences") or state.get("user_preferences", "None")
        concepts = mw_context.get("memory") or state.get("project_concepts", "None") # Mapped to project_concepts in tasks.py

        project_id = config.get("metadata", {}).get("project_id", 1)

        # 2. Tool Preparation
        tools = await self._get_tools(state)

        # 3. Prompt Construction
        prompt_builder = CoderPromptBuilder(
            plan=plan,
            context={
                "user_preferences": prefs,
                "project_concepts": concepts,
                "explicit_context": state.get("context", "")
            },
            project_id=project_id
        )

        system_msg = prompt_builder.build(config)

        # 4. FIX MODE Injection (QA Feedback)
        last_msg_content = ""
        messages = state.get("messages", [])
        if messages and isinstance(messages[-1].content, str):
            last_msg_content = messages[-1].content

        if "TEST PHASE: FAIL" in last_msg_content:
             system_msg += self._build_fix_mode_prompt(last_msg_content)

        # 5. Execution
        logger.info("Coder delegating to AgentEngine")

        return await AgentEngine.run_node(
            state=state,
            config=config,
            system_prompt=system_msg,
            tools=tools,
            name="Coder"
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
                 if rec['name'] in mcp_map:
                     dynamic_tools.append(mcp_map[rec['name']])

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

# Instance for Graph
coder_node = CoderNode()
