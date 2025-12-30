from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
import json
from langchain_core.runnables import RunnableConfig
from app.core.llm.factory import LLMFactory

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
    from app.domain.tools.execution import run_shell_command
    from app.domain.codebase.retrieval.tools import search_codebase
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
        run_shell_command, search_codebase, get_annotated_tree, 
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
    - get_annotated_tree(path): View project structure with indexed symbols.
    - write_file_content(path, content): Best for creating/editing files safely.
    - search_codebase(query): Combine Graph+RAG search to find code or usage.
    - run_command(command): Use for `ls`, `mkdir`, `mv`, `rm` or running tests/scripts.
    - save_preference(key, value): If user gives new instructions, save them.
    - add_concept(name, desc): If you learn a new architectural concept, save it.
    
    Use `write_file_content` for writing code. Use `run_command` for file management or verification.
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
            result = f"Error: Tool {tool_name} not found"
            if tool:
                try:
                    result = await tool.ainvoke(tool_args, config=config)
                except Exception as e:
                    result = str(e)
            
            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    return {
        "code": "Code implemented via tools",
        "messages": [AIMessage(content=f"Implementation complete. {generated_code_summary}")]
    }
