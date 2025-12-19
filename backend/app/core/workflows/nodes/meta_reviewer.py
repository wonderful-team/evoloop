from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from app.core.workflows.state import AgentState
from app.core.llm.factory import LLMFactory
from app.logging import logger

logger = logger.getChild("meta_reviewer")

llm = LLMFactory.create_llm(temperature=0.5)

reviewer_prompt = ChatPromptTemplate.from_template("""
You are the Meta-Reviewer, a Senior Technical Lead.
The engineering team (Coder & Tester) is stuck in a loop of failures.

Context:
Project ID: {project_id}
Current Plan: {plan}
Recent Failure: {test_results}
Iteration Count: {iteration_count}

Your Task:
Analyze the situation. Why are they failing? 
- Is the plan fundamentally flawed?
- Are they trying to fix a file that doesn't exist?
- Are they missing a dependency?
- Are they writing code that contradicts the existing architecture?

Provide a "Course Correction" directive to the Supervisor. 
Be specific about what they should STOP doing and what they SHOULD do instead.
Suggest a new angle or a step back to research if needed.
""")

async def meta_reviewer_node(state: AgentState):
    """
    Meta-Reviewer Node: Analyzes repeated failures and advises the Supervisor.
    """
    logger.info("Meta-Reviewer triggered.")
    
    project_id = state.get("project_id", 1)
    plan = state.get("current_plan", "Unknown")
    test_results = state.get("test_results", "Unknown Failure")
    iteration_count = state.get("iteration_count", 0)
    
    chain = reviewer_prompt | llm
    
    response = await chain.ainvoke({
        "project_id": project_id,
        "plan": plan,
        "test_results": test_results,
        "iteration_count": iteration_count
    })
    
    # We prefix the analysis to make it clear it's an intervention
    advice = f"**META-REVIEW INTERVENTION**:\n{response.content}"
    
    return {
        "messages": [AIMessage(content=advice)],
        # We might want to reset iteration count or flag intervention, 
        # but Supervisor logic handles the next step.
        # "technical_analysis": advice # Optionally update analysis
    }
