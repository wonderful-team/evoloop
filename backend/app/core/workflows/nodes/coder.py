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
    llm = LLMFactory.create_llm()
    messages = state["messages"]
    
    # Context injected by middleware
    plan = context.get("current_plan", "")
    prefs = context.get("user_preferences", "None")
    project_id = context.get("project_id", 1)
    concepts = context.get("memory", "None")
    
    # Explicit Context from State (e.g. Previous retrieval)
    # Some things might still live in state if they are transient
    retrieval_ctx = state.get("context", "")
    
    # Get tools
    # Core Tools Imports
    from app.domain.tools.profiles import get_profile_static_tools
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.vector_store import pg_tool_retriever

    # 1. Orchestration: Determine Profile & Query (Phase 3.0)
    profile_name = state.get("active_tool_profile") or "GENERAL"
    retrieval_query = state.get("tool_retrieval_query")
    
    # 2. Get Static Tools for Profile
    core_tools = get_profile_static_tools(profile_name)
    
    # 3. Dynamic Retrieval (Hybrid Binding)
    dynamic_tools = []
    if retrieval_query:
        # User defined dynamic query
        # Retrieve metadata first
        records = await pg_tool_retriever.search_tools(retrieval_query, k=5)
        
        # Hydrate into actual tools
        # For now, we fetch ALL MCP tools and filter. 
        # OPTIMIZATION TODO: Fetch only needed tools by name if MCP supports it.
        all_mcp_tools = mcp_client_manager.get_tools()
        mcp_map = {t.name: t for t in all_mcp_tools}
        
        for rec in records:
            if rec['name'] in mcp_map:
                dynamic_tools.append(mcp_map[rec['name']])

    # 4. Combine
    # Use dict to deduplicate
    tool_dict = {t.name: t for t in core_tools + dynamic_tools}
    tools = list(tool_dict.values())
    
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}
    
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

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
    
    ### LANGUAGE DIRECTIVE (STRICT)
    User Language Preference: **{user_lang}**.
    - **Code Comments**: Must be in {user_lang}.
    - **Docstrings**: Must be in {user_lang}.
    - **Explanations**: Must be in {user_lang}.
    
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
    
    ### DECISION TREE
    - Need to understand Module/Architecture? -> `consult_architecture`.
    - Need to see map? -> `manage_file(action='list_tree')`.
    - Need to find code? -> `explore_codebase`.
    - Need to read/edit code? -> `manage_file`.
    - Need to run tests? -> `run_command`.
    """
    
    # Check for recent Test Failure (Fix Mode)
    last_msg_content = ""
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
    
    # --- CONTEXT PINNING STRATEGY ---
    # To fix "Context Amnesia", we ensure the Original Goal (First Human Message) is always present.
    
    # 1. System Prompt (Always First)
    system_message = AIMessage(content=system_msg)
    
    # 2. Original Goal (Pinning)
    original_goal_message = None
    for m in messages:
        if m.type == "human":
            original_goal_message = m
            break
            
    # 3. Recent History (Sliding Window)
    # We take last 8 messages to give enough context for immediate tool loops.
    # CRITICAL FIX: Ensure we don't slice off the parent AIMessage of a ToolMessage.
    
    start_index = max(0, len(messages) - 8)
    recent_messages = messages[start_index:]
    
    # Check for Orphaned Tool Message at start
    while recent_messages and isinstance(recent_messages[0], ToolMessage):
        # Tools need their AI call. We must look backwards.
        start_index -= 1
        if start_index < 0:
             # Should not happen in valid history, but if it does, 
             # we cannot fix it by going back further.
             # In this case, we DROP the orphaned tool message to satisfy LLM API.
             recent_messages.pop(0)
             # Continue check in case next one is also tool
        else:
             # Prepend the previous message (hopefully the AIMessage)
             previous_msg = messages[start_index]
             recent_messages.insert(0, previous_msg)
             # Loops again to check if THAT message is also dependent (rare for AI, but safe)

    # Build Final Loop Messages
    loop_messages = [system_message]
    
    if original_goal_message:
        # If the original goal is NOT in recent messages, insert it explicitly as context reminder.
        is_in_recent = any(m.content == original_goal_message.content for m in recent_messages)
        
        if not is_in_recent:
            loop_messages.append(original_goal_message)
            
    loop_messages.extend(recent_messages)
    
    generated_code_summary = ""
    
    # Simple ReAct Loop
    for _ in range(5):
        response = await llm_with_tools.ainvoke(loop_messages, config=config)
        loop_messages.append(response)
        
        if not response.tool_calls:
            generated_code_summary = response.content
            break
            
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            # print(f"Coder [MCP Tool]: {tool_name} args={tool_args}")
            
            tool = tool_map.get(tool_name)
            executor = ToolExecutor()
            
            if tool:
                # Use executor for logging and error handling standardization
                result = await executor.execute(tool, tool_args, config=config)
            else:
                result = f"Error: Tool {tool_name} not found"
            
            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    msg = f"Implementation complete. {generated_code_summary}"
    
    return {
        "code": "Code implemented via tools",
        "messages": [AIMessage(content=msg)]
    }
