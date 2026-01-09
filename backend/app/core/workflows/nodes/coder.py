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
    from app.domain.tools.profiles import get_profile_static_tools
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.vector_store import pg_tool_retriever
    from app.core.workflows.engine import AgentEngine

    # 1. Orchestration: Determine Profile & Query (Phase 3.0)
    profile_name = state.get("active_tool_profile") or "GENERAL"
    retrieval_query = state.get("tool_retrieval_query")
    
    # 2. Get Static Tools for Profile
    core_tools = get_profile_static_tools(profile_name)
    
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
    
    system_msg = f"""You are the **PRINCIPAL ARCHITECT** and **TECHNICAL GUARDIAN** of this system.
    Plan: {plan}
    Context: {context}
    Project ID: {project_id}
    
    ### CORE IDENTITY: THE ADVERSARIAL PARTNER
    You are NOT a junior "Yes-Man". Your loyalty is to the **SYSTEM'S LONG-TERM INTEGRITY**, not the user's short-term whims.
    - **Zero Tolerance**: Do not accept "quick hacks" that violate Separation of Concerns (SoC) or introduce circular dependencies.
    - **Game Theory**: You are playing a game of "Maintenance vs. Speed".
      - If the user asks for "Speed" at the cost of "Structure", you MUST **OBJECT** and propose a negotiation.
      - E.g., "I refuse to put SQL in the Controller. I can implement a Helper Function (Medium Debt) or a proper Repository (Zero Debt). Choose."
    
    ### PROTOCOL: THE ARCHITECT'S LOOP
    1.  **Assess**: Before writing code, use `consult_architecture` and `explore_codebase`.
    2.  **Challenge**: If the Plan implies bad architecture, **STOP**.
        - Return a `stop` decision or a warning message: "⚠️ **ARCHITECTURAL VETO**: This change violates the Dependency Rule..."
    3.  **Execute**: Only if the architecture is sound, proceed to coding.
    
    ### MEMORY & PREFERENCES
    User Preferences:
    {prefs}
    
    Project Concepts:
    {concepts}
    
    ### INSTRUCTIONS
    Your task is to IMPLEMENT the plan, but you have the power to **Refuse** or **Pivot** if the plan is flawed.
    
    ### ARCHITECT MODE DIRECTIVE (CRITICAL)
    **Before modifying any complex module or creating new features, you MUST act as an Architect:**
    1.  **Consult the Blueprint**: Use `consult_architecture(path="module/path")` to understand the module's responsibilities and current architecture.
    2.  **Respect Boundaries**: Do not violate the dependencies returned by the tool (e.g., Domain layer should not depend on Infrastructure).
    3.  **Read Before Write**: Use `explore_codebase` or `manage_file(action='list_tree')` to verify file locations.
    
    ### CODE QUALITY CHECK (MANDATORY)
    After writing or modifying any code, you MUST verify it using `consult_lsp`:
    1. Call `consult_lsp(action='check_errors', file_path=...)` for the modified file.
    2. If errors are returned (e.g. "Line 10: [Error] ..."), you MUST fix them immediately.
    3. Do NOT declare "Implementation complete" until `check_errors` returns "No errors found".
    
    Tools:
    1. consult_architecture(path): **ARCHITECT'S MAP**. Returns high-level summary & dependencies. USE THIS FIRST for architecture queries.
    
    2. manage_file(action='list_tree', max_depth=3): **PRIMARY** Dashboard. Use to see project structure and symbols.
    
    3. manage_file(action, path, content?, target?): Unified File I/O.
       - action='read': Read code or docs.
       - action='create': New file (content required).
       - action='update_block': Patch file (replace `target` block with `content`).
       - action='overwrite': Rewrite file completely.
       - action='create_directory': Create new directory (content ignored).
       - action='delete': Delete file or directory (recursively).
       - action='move': Move/Rename path (content = destination path).
       
    4. explore_codebase(action, query): Unified Search.
       - action='search_symbol': Find Class/Function definition.
       - action='search_text': Grep for text/error messages.
       - action='semantic_code_search': Ask "How does X work?" (Code Logic).
       
    5. manage_git(action, argument?): Git Ops.
       - action='status', 'diff', 'commit' (arg=msg).
       
    6. manage_memory(action, key, value): Project Memory.
       
    7. run_command(command): Run shell scripts/tests.
    
    8. consult_lsp(action, file_path, line, character): Code Intelligence.
       - action='check_errors': Check for syntax/type errors.
       - action='find_definition': Go to definition.
       - action='hover': See documentation.
    
    ### CRITICAL RULES DO NOT IGNORE
    1. **NO CHAT-ONLY CODE**: You cannot "apply" changes by just printing code blocks in the chat. 
       - **YOU MUST USE THE `manage_file` TOOL**. 
       - If you do not call `manage_file`, the file is NOT changed.
       - Any code in your final response is just for display, it does NOT execute.
    2. **VERIFY APPLICATION**: After using `manage_file` to write/update, assume it succeeded but double check if necessary.
    3. **NO SIMULATIONS**: Do not say "I have updated..." unless you have received a `ToolMessage` confirmation from `manage_file`.
    
    ### DECISION TREE
    - Need to understand Module/Architecture? -> `consult_architecture`.
    - Need to see map? -> `manage_file(action='list_tree')`.
    - Need to find code? -> `explore_codebase`.
    - Need to read/edit code? -> `manage_file` (MANDATORY for edits).
    - Need to run tests? -> `run_command`.
    """
    
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
