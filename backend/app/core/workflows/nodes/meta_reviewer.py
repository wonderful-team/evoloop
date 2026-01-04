from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from app.core.workflows.state import AgentState
from app.core.llm.factory import LLMFactory
from app.logging import logger

logger = logger.getChild("meta_reviewer")


async def meta_reviewer_node(state: AgentState, config: RunnableConfig):
    """
    Meta-Reviewer Node: Analyzes repeated failures and advises the Supervisor.
    """
    llm = LLMFactory.create_llm(temperature=0.5)

    # 0. Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    reviewer_prompt = ChatPromptTemplate.from_template("""
You are the Meta-Reviewer, a Senior Technical Lead.
The engineering team (Coder & Tester) is stuck in a loop of failures.

Context:
Project ID: {project_id}
Current Plan: {plan}
Recent Failure: {test_results}
Iteration Count: {iteration_count}

Project Structure (Architecture):
{tree}

LANGUAGE PROTOCOL (STRICT):
User Preference: {user_lang}
You MUST write your analysis and advice in {user_lang}.

Your Task:
Analyze the situation. Why are they failing? 
- Is the plan fundamentally flawed?
- Are they trying to fix a file that doesn't exist? (Check Structure)
- Are they missing a dependency?
- Are they writing code that contradicts the existing architecture?

Provide a "Course Correction" directive to the Supervisor. 
Be specific about what they should STOP doing and what they SHOULD do instead.
Suggest a new angle or a step back to research if needed.
""")

    logger.info("Meta-Reviewer triggered.")
    
    project_id = state.get("project_id", 1)
    plan = state.get("current_plan", "Unknown")
    test_results = state.get("test_results", "Unknown Failure")
    iteration_count = state.get("iteration_count", 0)
    
    # 1. Get Architectural Context
    import os
    from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
    
    # Resolve root
    root = config.get("configurable", {}).get("working_directory") or os.getcwd()
    
    try:
        # Depth 2 is usually enough for high-level architecture
        generator = AnnotatedTreeGenerator(root, max_depth=3, with_symbols=False, file_limit=30)
        tree_context = await generator.generate()
        
        # Smart Truncation enabled in Generator (file_limit=30)
    except Exception as e:
        tree_context = f"Error fetching architecture: {e}"

    chain = reviewer_prompt | llm
    
    response = await chain.ainvoke({
        "project_id": project_id,
        "plan": plan,
        "test_results": test_results,
        "iteration_count": iteration_count,
        "tree": tree_context,
        "user_lang": user_lang
    }, config=config)
    
    # We prefix the analysis to make it clear it's an intervention
    advice = f"**META-REVIEW INTERVENTION**:\n{response.content}"
    
    return {
        "messages": [AIMessage(content=advice)],
        # We might want to reset iteration count or flag intervention, 
        # but Supervisor logic handles the next step.
        # "technical_analysis": advice # Optionally update analysis
    }
