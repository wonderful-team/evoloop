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
    tools = get_all_tools()
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}
    
    prefs = state.get("user_preferences", "None")
    project_id = state.get("project_id", 1)
    
    system_msg = f"""You are a Senior Software Engineer.
    Plan: {plan}
    Context: {context}
    User Preferences: {prefs}
    Project ID: {project_id}
    
    Your task is to IMPLEMENT the plan by writing code to files.
    
    Tools:
    - get_annotated_tree(path): View project structure with indexed symbols.
    - write_file_content(path, content): Best for creating/editing files safely.
    - run_command(command): Use for `ls`, `mkdir`, `mv`, `rm` or running tests/scripts.
    
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
