from functools import partial

from langgraph.graph import END, StateGraph

from app.core.engine.nodes.coder import coder_node

# For Evolution, we might want a simpler planner or reuse the main one with special context.
# Let's reuse planner for now but maybe inject special prompt?
# Or just use the Generic Node for "Evolution Planner" as described in the plan.
# Let's make an explicit EvolutionPlanner for clarity.
from app.core.engine.nodes.generic import generic_node
from app.core.engine.nodes.system_scanner import system_scanner_node
from app.core.engine.nodes.tester import tester_node
from app.core.engine.state import AgentState

# Evolution Planner Config
evolution_planner_config = {
    "system_prompt": """You are the **Evolution Architect**.
Your goal is to design a code change to FIX the systemic issue identified by the System Scanner.

Input:
- Health Report: {evolution_report}

Instructions:
1. Create a detailed plan to modify the codebase.
2. The plan MUST be on a NEW git branch.
3. The plan MUST include a regression test.

Output:
- Use `create_plan` tool to formalize the plan.
""",
    "tools": ["create_plan", "analyze_feasibility"],
}

evolution_planner_node = partial(generic_node, node_config=evolution_planner_config)
evolution_planner_node.__name__ = "evolution_planner"

# Graph Definition
workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("system_scanner", system_scanner_node)
workflow.add_node("evolution_planner", evolution_planner_node)
workflow.add_node("coder", coder_node)
workflow.add_node("tester", tester_node)

# Edges
workflow.set_entry_point("system_scanner")


# Scanner -> Planner (if issue found) OR End (if healthy)
def route_scanner(state):
    if state.get("evolution_report"):
        return "evolution_planner"
    return END


workflow.add_conditional_edges(
    "system_scanner",
    route_scanner,
    {"evolution_planner": "evolution_planner", END: END},
)

# Planner -> Coder
workflow.add_edge("evolution_planner", "coder")

# Coder -> Tester
workflow.add_edge("coder", "tester")

# Tester -> End (for now, simplistic)
# Realistically: Tester -> Merge (if success) or Revert (if fail)
workflow.add_edge("tester", END)

evolution_graph = workflow.compile()
