from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from app.core.workflows.state import AgentState
from app.core.workflows.nodes.supervisor import supervisor_node

from app.core.workflows.nodes.coder import coder_node
from app.core.workflows.nodes.tester import tester_node
from app.core.workflows.nodes.deep_researcher import deep_researcher_node
from app.core.workflows.nodes.documenter import documenter_node
from app.core.workflows.nodes.meta_reviewer import meta_reviewer_node


def create_graph(checkpointer=None):
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("supervisor", supervisor_node)

    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("deep_researcher", deep_researcher_node)
    workflow.add_node("documenter", documenter_node)
    workflow.add_node("meta_reviewer", meta_reviewer_node)

    # Set Entry Point
    workflow.set_entry_point("supervisor")

    # Add Edges from Supervisor
    # Add Edges from Supervisor
    
    def route_supervisor(state: AgentState):
        next_node = state["next_node"]
        if next_node == "map_research":
            tasks = state.get("parallel_research_tasks", [])
            return [Send("deep_researcher", {"research_topic": topic}) for topic in tasks]
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
            "finish": END
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
            if state["iteration_count"] > 3:
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
    if checkpointer:
        return workflow.compile(checkpointer=checkpointer)
    else:
        return workflow.compile()
