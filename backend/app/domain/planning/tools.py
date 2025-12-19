import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from typing import List, Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from app.domain.codebase.retrieval.service import RetrievalService
from app.domain.tools.visualizer import get_annotated_tree
from app.core.llm.factory import LLMFactory
from .models import Plan, Step

logger = logging.getLogger(__name__)
llm = LLMFactory.create_llm()

FEASIBILITY_ANALYSIS_PROMPT = ChatPromptTemplate.from_template("""
You are a Technical Architect ensuring the feasibility of a development plan.

Proposed Plan:
{plan}

Codebase Context (Retrieved Symbols):
{context}

Project Structure (Tree):
{tree}

Analyze the plan for the following risks:
1. **Hallucination**: Does the plan modify files or classes that do not exist?
2. **Dependency Issues**: Will imports break (e.g. circular imports, missing modules)?
3. **API Contracts**: Does it change a public method signature used elsewhere without updating callers?
4. **Complexity**: Is the plan too vague or too complex for a single iteration?

Return a strict analysis report in Markdown:
- **Status**: [FEASIBLE / RISKY / BLOCKER]
- **Risk Score**: (0-10, 10 is impossible)
- **Validation Details**:
    - Confirmed Symbols: (List symbols found)
    - Missing Symbols: (List symbols not found)
    - Impact Analysis: (Briefly describe impact)
- **Recommendations**: (Specific actions to fix the plan)
""")

class CreatePlanInput(BaseModel):
    title: str = Field(..., description="High level goal of the plan")
    steps: List[str] = Field(..., description="List of step titles")

class UpdatePlanInput(BaseModel):
    plan_id: str = Field(..., description="ID of the plan to update")
    step_id: str = Field(..., description="ID of the step to update")
    status: str = Field(..., description="New status: pending, in_progress, completed, failed")
    result: Optional[str] = Field(None, description="Result of the step")

class PlanningTool(BaseTool):
    name: str = "planning_tool"
    description: str = "Create or update a plan. Use this tool BEFORE starting any complex task to outline your steps."
    
    def _run(self, action: str, **kwargs) -> str:
        """
        Action can be 'create' or 'update'.
        For 'create', provide 'title' and 'steps' (list of strings).
        For 'update', provide 'plan_id', 'step_id', 'status', 'result'.
        """
        if action == "create":
            title = kwargs.get("title")
            step_titles = kwargs.get("steps", [])
            steps = [Step(title=t) for t in step_titles]
            plan = Plan(title=title, steps=steps)
            if steps:
                plan.current_step_id = steps[0].id
                steps[0].status = "in_progress"
            
            # scalable: meaningful return so LLM knows what it did
            return json.dumps(plan.model_dump(), ensure_ascii=False)
            
        elif action == "update":
            # In a real implementation with LangGraph, the 'tool' might not persist state directly 
            # if it's stateless. But here we simulate the logic.
            # The actual persistence happens when Supervisor invokes this and we save to checkingpointer or return plain dict
            # that Supervisor uses to patch state.
            pass
            
        return "Invalid action"
        
    def _arun(self, action: str, **kwargs):
        raise NotImplementedError("Async not implemented")

# For LangGraph integration, we might prefer using structured tools or simply functions.
# Let's define a function-based tool for easier binding with LangChain.

from langchain_core.tools import tool

@tool
def create_plan(title: str, steps: List[str]):
    """
    Create a detailed plan for the task.
    Args:
        title: The main goal.
        steps: A list of step descriptions.
    """
    plan_steps = [Step(title=t) for t in steps]
    plan = Plan(title=title, steps=plan_steps)
    if plan_steps:
        plan.current_step_id = plan_steps[0].id
        plan_steps[0].status = "in_progress"
    return plan.model_dump_json()

@tool
def update_step_status(plan_id: str, step_id: str, status: str, result: str = None):
    """
    Update the status of a step in the plan.
    """
    # This function is pure logic, the state update happens in the Node.
    return json.dumps({
        "action": "update_step",
        "plan_id": plan_id,
        "step_id": step_id,
        "status": status,
        "result": result
    })

@tool
def analyze_feasibility(proposed_plan: str) -> str:
    """
    Analyze the technical feasibility of a proposed development plan.
    It retrieves relevant code context and checks for potential issues like hallucinations or breaking changes.
    Args:
        proposed_plan: The detailed plan step-by-step.
    """
    try:
        # Retrieval
        retrieval_service = RetrievalService()
        search_results = retrieval_service.search(proposed_plan, limit=5)
        
        context_str = "\n".join([f"File: {r['file_path']}\nSnippet: {r['content'][:500]}..." for r in search_results])
        
        # Get Project Structure
        tree = get_annotated_tree(".", max_depth=2)
        
        # LLM Analysis
        chain = FEASIBILITY_ANALYSIS_PROMPT | llm | StrOutputParser()
        report = chain.invoke({
            "plan": proposed_plan,
            "context": context_str,
            "tree": tree
        })
        
        return report
        
    except Exception as e:
        logger.error(f"Feasibility analysis failed: {e}")
        return f"Analysis Failed: {str(e)}"
