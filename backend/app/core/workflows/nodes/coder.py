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
    from app.infrastructure.filesystem.tool import list_files, read_file, grep_files, write_file_content, edit_file
    from app.infrastructure.filesystem.tool import list_files, read_file, grep_files, write_file_content, edit_file
    from app.domain.tools.execution import run_command
    from app.domain.codebase.retrieval.tools import search_codebase
    from app.domain.codebase.analysis.tools import find_definition
    from app.domain.tools.visualizer import get_annotated_tree
    from app.domain.tools.memory import save_preference, add_concept
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.retrieval import tool_retriever
    from app.domain.tools.git import git_status, git_diff, git_commit, git_history, git_create_branch

    # 1. Define Core (Standard Dev Tools)
    core_tools = [
        # File Ops
        list_files, read_file, grep_files, write_file_content, edit_file,
        # Git Ops
        git_status, git_diff, git_commit, git_history, git_create_branch,
        # Analysis
        run_command, search_codebase, get_annotated_tree, find_definition, 
        # Memory
        save_preference, add_concept
    ]
    
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
    - Respect the User Preferences above (e.g. testing frameworks, naming conventions).
    - Use the Project Concepts to understand existing architecture names.
    
    Tools:
    - get_annotated_tree(path): **PRIMARY** tool to see project structure. Prefer this over `list_files`.
    - find_definition(symbol): Use this to find where a Class or Function is defined.
    - search_codebase(query): Use this for "How does X work?" (Concept/Semantic Search).
    - grep_files(pattern): Use this for exact text search (error msg, references).
    - edit_file(path, target, replacement): Use for **SMALL** edits (< 50 lines). Requires exact match.
    - write_file_content(path, content): Use for NEW files or **LARGE** refactors.
    - run_command(command): Run tests/scripts.
    
    ### DECISION TREE (Follow Strict)
    1. Need to understand structure? -> `get_annotated_tree`.
    2. Need to find a class definition? -> `find_definition`.
    3. Need to fix a bug?
       - Locate file with `grep_files` or `find_definition`.
       - Read context with `read_file`.
       - If small fix -> `edit_file`.
       - If huge refactor -> `write_file_content`.
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
