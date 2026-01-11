from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
import json
from langchain_core.runnables import RunnableConfig
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor
from app.core.workflows.middleware import context_aware


@context_aware(inject=["current_plan", "user_preferences", "memory", "project_id"])
async def coder_node(state: AgentState, config: RunnableConfig, context: dict = None):
    """
    Coder Node:
    1. Reads plan.
    2. Writes code using MCP tools.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Context injected by middleware
    plan = context.get("current_plan", "")
    prefs = context.get("user_preferences", "None")
    project_id = context.get("project_id", 1)
    concepts = context.get("memory", "None")
    
    # Explicit Context from State (e.g. Previous retrieval)
    retrieval_ctx = state.get("context", "")
    
    # Get tools
    # Core Tools Imports
    from app.core.tools.registry_utils import get_node_tools
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.vector_store import pg_tool_retriever
    from app.core.workflows.engine import AgentEngine

    # 1. Orchestration: Determine Profile & Query (Phase 3.0)
    profile_name = state.get("active_tool_profile") or "GENERAL"
    retrieval_query = state.get("tool_retrieval_query")
    
    # 2. Get Static Tools for Profile (RBAC)
    core_tools = get_node_tools("coder")
    
    # 3. Dynamic Retrieval (Hybrid Binding)
    dynamic_tools = []
    if retrieval_query:
        # User defined dynamic query
        records = await pg_tool_retriever.search_tools(retrieval_query, k=5)
        
        # Hydrate into actual tools
        all_mcp_tools = mcp_client_manager.get_tools()
        mcp_map = {t.name: t for t in all_mcp_tools}
        
        for rec in records:
            if rec['name'] in mcp_map:
                dynamic_tools.append(mcp_map[rec['name']])

    # 4. Combine
    tool_dict = {t.name: t for t in core_tools + dynamic_tools}
    tools = list(tool_dict.values())
    
    # Construst System Prompt using Modular Builder (Phase 5)
    from app.core.prompts.coder_builder import CoderPromptBuilder
    
    prompt_builder = CoderPromptBuilder(
        plan=plan,
        context={
            "user_preferences": prefs,
            "project_concepts": concepts,
            "explicit_context": context # merge explicit dict if needed
        },
        project_id=project_id
    )
    
    system_msg = prompt_builder.build(config)
    
    # Check for recent Test Failure (Fix Mode)
    last_msg_content = ""
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1].content, str):
        last_msg_content = messages[-1].content
        
    if "TEST PHASE: FAIL" in last_msg_content:
        system_msg += f"""
        
        !!! CRITICAL: FIX MODE ACTIVATED !!!
        The previous tests FAILED. You are now in FIX MODE.
        
        FEEDBACK FROM QA:
        {last_msg_content}
        
        PROTOCOL:
        1. Read the failing file and the test file.
        2. Apply the 'FIX SUGGESTION' provided above if it makes sense.
        3. Verify the fix by running the test.
        """
        
    # Delegate to Engine
    logger.info("Coder delegating to AgentEngine")
    
    return await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_msg,
        tools=tools,
        name="Coder"
    )
