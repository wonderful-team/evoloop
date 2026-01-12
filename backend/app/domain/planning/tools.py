import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.logging import get_context

from .models import Plan, Step

logger = logging.getLogger(__name__)

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

LANGUAGE PROTOCOL (STRICT):
User Language: {user_lang}
You MUST write the analysis report (Risk Score, Validation Details, Recommendations) in {user_lang}.
""")


class CreatePlanInput(BaseModel):
    title: str = Field(..., description="High level goal of the plan")
    steps: list[str] = Field(..., description="List of step titles")


class UpdatePlanInput(BaseModel):
    plan_id: str = Field(..., description="ID of the plan to update")
    step_id: str = Field(..., description="ID of the step to update")
    status: str = Field(..., description="New status: pending, in_progress, completed, failed")
    result: str | None = Field(None, description="Result of the step")


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


@tool
def create_plan(title: str, steps: list[str]):
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
async def update_step_status(plan_id: str, step_id: str, status: str, result: str = None, execution_run_id: str = None):
    """
    Update the status of a step in the plan.
    Args:
        plan_id: The ID of the plan.
        step_id: The ID of the step.
        status: New status (pending, in_progress, completed, failed).
        result: Optional result description.
        execution_run_id: Optional ID of the current agent run executing this step.
    """
    from app.domain.planning.models import (
        PlanStep,  # Ensure this is correct import or use app.infrastructure.database.sql.models
    )
    from app.infrastructure.database.sql.database import session_scope

    # Use the shared models from infrastructure to match session definition
    from app.infrastructure.database.sql.models import PlanStep

    try:
        async with session_scope() as session:
            step = await session.get(PlanStep, step_id)
            if step:
                step.status = status
                if result:
                    step.result = result
                if execution_run_id:
                    step.execution_run_id = execution_run_id

                # session commits automatically on exit
            else:
                 return json.dumps({"error": "Step not found"})

        return json.dumps({
            "action": "update_step",
            "plan_id": plan_id,
            "step_id": step_id,
            "status": status,
            "result": result,
            "execution_run_id": execution_run_id
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def analyze_feasibility(proposed_plan: str, config: RunnableConfig) -> str:
    """
    Analyze the technical feasibility of a proposed development plan.
    It retrieves relevant code context and checks for potential issues like hallucinations or breaking changes.
    Args:
        proposed_plan: The detailed plan step-by-step.
    """
    ctx = get_context()
    project_id = ctx.get("project_id", 1)
    root = ctx.get("working_directory", ".")

    try:
        # Retrieval
        from app.domain.codebase.retrieval.service import RetrievalService
        retrieval_service = RetrievalService()
        search_results = await retrieval_service.search(proposed_plan, project_id=project_id, limit=5)

        context_str = "\n".join([f"File: {r['file_path']}\nSnippet: {r['content'][:500]}..." for r in search_results])

        # Get Project Structure
        # Use underlying Generator directly (no longer a tool)
        from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
        # Smart Truncation enabled to avoid context overflow
        generator = AnnotatedTreeGenerator(root, max_depth=3, with_symbols=False, file_limit=30)
        tree = await generator.generate()

        # LLM Analysis
        from app.core.llm.factory import LLMFactory
        llm = LLMFactory.create_llm()
        from app.domain.system.service import SystemConfigService
        user_lang = SystemConfigService.get_language_preference()

        chain = FEASIBILITY_ANALYSIS_PROMPT | llm | StrOutputParser()
        report = await chain.ainvoke({
            "plan": proposed_plan,
            "context": context_str,
            "tree": tree,
            "user_lang": user_lang
        }, config=config)

        return report

    except Exception as e:
        logger.error(f"Feasibility analysis failed: {e}")
        return f"Analysis Failed: {str(e)}"
