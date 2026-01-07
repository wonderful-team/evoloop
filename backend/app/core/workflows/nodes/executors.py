from app.core.workflows.state import AgentState
from app.domain.tools.browser import browser_agent
from app.domain.tools.computer import computer_agent_tool
from app.domain.tools.mobile import mobile_agent_tool
from langchain_core.messages import ToolMessage


async def browser_executor(state: AgentState):
    instruction = state.get("refined_instruction") or state["messages"][-1].content
    # Directly invoke tool
    result = await browser_agent._arun(instruction)
    return {"messages": [ToolMessage(content=str(result), tool_call_id="browser_exec", name="browser_agent")]}


async def computer_executor(state: AgentState):
    instruction = state.get("refined_instruction") or state["messages"][-1].content
    result = await computer_agent_tool._arun(instruction)
    return {"messages": [ToolMessage(content=str(result), tool_call_id="computer_exec", name="computer_agent")]}


async def mobile_executor(state: AgentState):
    instruction = state.get("refined_instruction") or state["messages"][-1].content
    result = await mobile_agent_tool._arun(instruction)
    return {"messages": [ToolMessage(content=str(result), tool_call_id="mobile_exec", name="mobile_agent")]}
