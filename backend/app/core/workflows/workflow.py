from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from app.core.workflows.state import AgentState
from app.core.workflows.nodes.supervisor import supervisor_node

from app.core.workflows.nodes.coder import coder_node
from app.core.workflows.nodes.tester import tester_node
from app.core.workflows.nodes.deep_researcher import deep_researcher_node
from app.core.workflows.nodes.documenter import documenter_node
from app.core.workflows.nodes.meta_reviewer import meta_reviewer_node
from app.core.workflows.nodes.router import router_node
from app.core.workflows.nodes.finish import finish_node
from app.domain.tools.browser import browser_agent
from app.domain.tools.computer import computer_agent_tool
from app.domain.tools.mobile import mobile_agent_tool
from langchain_core.messages import ToolMessage


# Executor Nodes
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

def create_graph(checkpointer=None):
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("router", router_node)
    workflow.add_node("supervisor", supervisor_node)
    
    workflow.add_node("browser_executor", browser_executor)
    workflow.add_node("computer_executor", computer_executor)
    workflow.add_node("mobile_executor", mobile_executor)

    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("deep_researcher", deep_researcher_node)
    workflow.add_node("documenter", documenter_node)
    workflow.add_node("meta_reviewer", meta_reviewer_node)

    workflow.add_node("finish", finish_node)

    # Set Entry Point
    workflow.set_entry_point("router")
    
    # Router Logic
    workflow.add_conditional_edges(
        "router",
        lambda x: x["next_node"],
        {
            "supervisor": "supervisor",
            "browser_executor": "browser_executor",
            "computer_executor": "computer_executor",
            "mobile_executor": "mobile_executor"
        }
    )
    
    # Executor Logic - Return to Supervisor (or Finish?)
    # For now, return to supervisor to report completion/failure
    workflow.add_edge("browser_executor", "supervisor")
    workflow.add_edge("computer_executor", "supervisor")
    workflow.add_edge("mobile_executor", "supervisor")
    
    # Finish Logic
    workflow.add_edge("finish", END)

    # Add Edges from Supervisor
    
    def route_supervisor(state: AgentState):
        next_node = state["next_node"]
        if next_node == "map_research":
            tasks = state.get("parallel_research_tasks", [])
            project_id = state.get("project_id", 1)
            # Pass full context needed for research
            return [Send("deep_researcher", {
                "research_topic": topic,
                "project_id": project_id,
            }) for topic in tasks]
        if next_node == "finish":
            return "finish"
        return next_node

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "coder": "coder",
            "deep_researcher": "deep_researcher",
            "documenter": "documenter",
            "supervisor": "supervisor",
            "finish": "finish"
        }
    )

    # Deep Researcher logic (Self-loop or back to Supervisor)
    workflow.add_conditional_edges(
        "deep_researcher",
        lambda x: x["next_node"],
        {
            "deep_researcher": "deep_researcher",
            "supervisor": "supervisor"
        }
    )

    # Documenter Logic
    workflow.add_edge("documenter", "supervisor")
    
    # Meta-Reviewer Logic
    workflow.add_edge("meta_reviewer", "supervisor")

    # Coder -> Tester
    workflow.add_edge("coder", "tester")

    # Tester Logic
    def route_tester(state: AgentState):
        if state.get("test_results") == "PASS":
            return "supervisor"  # Let supervisor decide if we are done
        else:
            # Simple retry logic: if fail, go back to coder
            # In V3 advanced, we might go back to researcher or supervisor
            if state.get("iteration_count", 0) > 3:
                return "meta_reviewer"  # Intervention!
            return "coder"

    workflow.add_conditional_edges(
        "tester",
        route_tester,
        {
            "supervisor": "supervisor",
            "coder": "coder",
            "meta_reviewer": "meta_reviewer"
        }
    )

    # Add Checkpointer for auto-saving state
    # Human-in-the-Loop: Interrupt BEFORE supervisor to allow user approval
    if checkpointer:
        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["supervisor"]  # Pause before supervisor for HITL
        )
    else:
        return workflow.compile()
