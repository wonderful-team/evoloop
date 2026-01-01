from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
import json
from langchain_core.runnables import RunnableConfig
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor

llm = LLMFactory.create_llm()


async def coder_node(state: AgentState, config: RunnableConfig):
    """
    Coder Node:
    1. Reads plan.
    2. Writes code using MCP tools.
    """
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
    
    system_msg = f"""You are a Senior Software Engineer.
    Plan: {plan}
    Context: {context}
    Project ID: {project_id}
    
    ### MEMORY & PREFERENCES
    User Preferences:
    {prefs}
    
    Project Concepts / Terminology:
    {concepts}
    
    ### INSTRUCTIONS
    Your task is to IMPLEMENT the plan by writing code to files.
    - **PROTOCOL**: Do NOT guess file paths. If a path is ambiguous, use `get_annotated_tree` or `explore_codebase` BEFORE reading/editing.
    - Respect the User Preferences above (e.g. testing frameworks, naming conventions).
    - Use the Project Concepts to understand existing architecture names.
    
    Tools:
    1. get_annotated_tree(path): **PRIMARY** Dashboard. Use to see project structure.
    
    2. manage_file(action, path, content?, target?): Unified File I/O.
       - action='read': Read code or docs.
       - action='create': New file (content required).
       - action='update_block': Patch file (replace `target` block with `content`).
       - action='overwrite': Rewrite file completely.
       - action='create_directory': Create new directory (content ignored).
       - action='delete': Delete file or directory (recursively).
       - action='move': Move/Rename path (content = destination path).
       
    3. explore_codebase(action, query): Unified Search.
       - action='search_symbol': Find Class/Function definition.
       - action='search_text': Grep for text/error messages.
       - action='search_concept': Ask "How does X work?".
       
    4. manage_git(action, argument?): Git Ops.
       - action='status', 'diff', 'commit' (arg=msg).
       
    5. manage_memory(action, key, value): Project Memory.
       
    6. run_command(command): Run shell scripts/tests.
    
    ### DECISION TREE
    - Need to see map? -> `get_annotated_tree`.
    - Need to find code? -> `explore_codebase`.
    - Need to read/edit code? -> `manage_file`.
    - Need to run tests? -> `run_command`.
    """
    
    loop_messages = [AIMessage(content=system_msg)] + messages[-5:]
    
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
