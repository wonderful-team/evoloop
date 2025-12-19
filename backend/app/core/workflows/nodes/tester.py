from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.workflows.state import AgentState
from app.domain.tools.registry import get_all_tools
import json

from app.core.llm.factory import LLMFactory

llm = LLMFactory.create_llm()

from langchain_core.runnables import RunnableConfig


async def tester_node(state: AgentState, config: RunnableConfig):
    """
    Intelligent Tester:
    1. Looks at what Coder did.
    2. Decides what test to run.
    3. Executes test via MCP `run_command`.
    4. Reports PASS/FAIL.
    """
    messages = state["messages"]

    # Tester System Prompt
    system_msg = """You are a QA Engineer.
    The Coder has just written/modified code. Your job is to VERIFY it.
    
    Tools:
    - run_command(command): Run tests (e.g., `pytest`, `python -m ...`).
    - browser_agent(task): Use a browser to verify web apps (e.g., "Open localhost:3000 and check login").
    
    Strategy:
    1. Identify what files changed (look at context or recent messages).
    2. Run relevant tests. If no tests exist, try to run the code itself (e.g. `python path/to/file.py`) to check for syntax errors.
    3. If tests fail, report the EXACT error message.
    4. If tests pass, report PASS.
    
    Always output a summary starting with "PASS" or "FAIL".
    """

    # Get tools
    tools = get_all_tools()
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    loop_messages = [AIMessage(content=system_msg)] + messages[-3:]  # Context

    final_status = "FAIL"  # Default to fail if unsure

    for _ in range(3):
        response = await llm_with_tools.ainvoke(loop_messages, config=config)
        loop_messages.append(response)

        if not response.tool_calls:
            # Agent finished
            content = response.content.upper()
            if "PASS" in content and "FAIL" not in content:
                final_status = "PASS"
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            # print(f"Tester [MCP Tool]: {tool_name} args={tool_args}")

            tool = tool_map.get(tool_name)
            result = f"Error: Tool {tool_name} not found"
            if tool:
                try:
                    result = await tool.ainvoke(tool_args, config=config)
                except Exception as e:
                    result = str(e)

            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    return {
        "test_results": final_status,
        "messages": [AIMessage(content=f"Test Phase Complete. Result: {final_status}")]
    }
