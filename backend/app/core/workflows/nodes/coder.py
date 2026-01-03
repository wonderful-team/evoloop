from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
import json
from langchain_core.runnables import RunnableConfig
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor


async def coder_node(state: AgentState, config: RunnableConfig):
    """
    Coder Node:
    1. Reads plan.
    2. Writes code using MCP tools.
    """
    llm = LLMFactory.create_llm()
    messages = state["messages"]
    context = state.get("context", "")
    plan = state.get("current_plan", "")
    
    # Get tools
    # Core Tools Imports
    from app.domain.tools.registry import get_coder_tools
    from app.domain.tools.facades import manage_file, explore_codebase, manage_git, manage_memory
    from app.domain.tools.execution import run_command
    from app.domain.tools.visualizer import get_annotated_tree
    
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.retrieval import tool_retriever
    
    # 1. Get Base Tools from Registry
    core_tools = get_coder_tools()
    
    # 2. Retrieve Candidate Tools (MCP)
    mcp_tools = mcp_client_manager.get_tools()
    await tool_retriever.index_tools(mcp_tools)
    
    query = f"{plan} {context}"
    retrieved_tools = await tool_retriever.retrieve(query, k=10)
    
    # 3. Combine
    tool_dict = {t.name: t for t in core_tools + retrieved_tools}
    tools = list(tool_dict.values())
    
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}
    
    prefs = state.get("user_preferences", "None")
    project_id = state.get("project_id", 1)
    concepts = state.get("project_concepts", "None")
    
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
    3.  **Read Before Write**: Use `explore_codebase` or `get_annotated_tree` to verify file locations.
    
    Tools:
    1. consult_architecture(path): **ARCHITECT'S MAP**. Returns high-level summary & dependencies. USE THIS FIRST for architecture queries.
    
    2. get_annotated_tree(path): **PRIMARY** Dashboard. Use to see project structure.
    
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
    
    ### DECISION TREE
    - Need to understand Module/Architecture? -> `consult_architecture`.
    - Need to see map? -> `get_annotated_tree`.
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
    # Note: If messages list is short, overlap is handled by slicing logic.
    recent_messages = messages[-8:]
    
    # Build Final Loop Messages
    loop_messages = [system_message]
    
    if original_goal_message:
        # If the original goal is NOT in recent messages, insert it explicitly as context reminder.
        # Check by object identity or content? Content is safer.
        is_in_recent = any(m.content == original_goal_message.content for m in recent_messages)
        
        if not is_in_recent:
            # We add a "Reminder" of the original goal
            # Or just inject the message itself. 
            # Injecting message itself might confuse LLM flow if timestamps imply it was long ago.
            # Better strategy: Append a High-Level Reminder to system prompt? 
            # Or just put it after system prompt.
            loop_messages.append(original_goal_message)
            
            # Add a separator or context note?
            # "Below is the recent conversation history..." (Implicit)
            
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

    return {
        "code": "Code implemented via tools",
        "messages": [AIMessage(content=f"Implementation complete. {generated_code_summary}")]
    }
