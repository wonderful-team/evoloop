import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from sqlalchemy import delete, select

from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from .schemas import Plan, Step

logger = logging.getLogger(__name__)


def _render_analysis_prompt(plan: str, context: str, tree: str, user_lang: str) -> str:
    """Render the feasibility analysis prompt from Jinja2 template."""
    from app.utils import render_template
    return render_template(
        "domain/planning/feasibility_analysis.prompt.j2",
        plan=plan,
        context=context,
        tree=tree,
        user_lang=user_lang
    )


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
            title_str = str(title) if title is not None else "Untitled Plan"
            steps = [Step(title=str(t)) for t in step_titles]
            plan = Plan(title=title_str, steps=steps)
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


@evoloop_tool
async def create_plan(title: str, steps: list[str], config: RunnableConfig) -> str:
    """
    Create a detailed plan for the task and persist it to the database.
    Args:
        title: The main goal.
        steps: A list of step descriptions.
    """
    # Imports inside to avoid circular dependencies during initial load
    from app.infrastructure.database.sql.database import session_scope
    from app.models.planning import Plan as DBPlan
    from app.models.planning import PlanStep as DBPlanStep
    from app.utils.id import gen_uuid

    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return json.dumps({"error": "Missing thread_id in config"})

    try:
        async with session_scope() as session:
            # 1. Clean up old active plans for this thread OR Reuse current one
            stmt = select(DBPlan).where(DBPlan.thread_id == thread_id)
            result = await session.execute(stmt)
            existing_plan = result.scalar_one_or_none()

            if existing_plan:
                logger.info(f"Existing plan found plan_id={existing_plan.id} for thread={thread_id}. Updating.")
                plan_id = existing_plan.id
                existing_plan.title = title
                existing_plan.status = "active"

                # Delete old steps for this plan to overwrite with new ones (simplest approach for 'create_plan')
                # Alternatively we could soft-delete or archive, but 'create_plan' implies a fresh start.
                await session.execute(delete(DBPlanStep).where(DBPlanStep.plan_id == plan_id))
            else:
                # 2. Create Plan
                plan_id = gen_uuid()
                new_plan = DBPlan(
                    id=plan_id,
                    thread_id=thread_id,
                    title=title,
                    status="active"
                )
                session.add(new_plan)

            # 3. Create Steps (Common for both paths)
            db_steps = []
            for idx, step_title in enumerate(steps):
                step_id = gen_uuid()
                status = "in_progress" if idx == 0 else "pending"

                db_step = DBPlanStep(
                    id=step_id,
                    plan_id=plan_id,
                    title=step_title,
                    status=status,
                    order=idx,
                )
                session.add(db_step)
                db_steps.append(db_step)

            # Commit happens on exit

            # 4. Construct Return Object (Pydantic-like for Planner state)
            # We return the structure matching domain.planning.models.Plan
            # But populated with the DB IDs so future tools can reference them.

            return json.dumps({
                "id": plan_id,
                "title": title,
                "steps": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "status": s.status
                    } for s in db_steps
                ],
                "current_step_id": db_steps[0].id if db_steps else None,
                "is_complete": False
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Failed to create plan in DB: {e}")
        return json.dumps({"error": str(e)})


@evoloop_tool(
    is_hidden=True,  # Internal plan step tracking, not user-facing
)
async def update_step_status(
    plan_id: str,
    step_id: str,
    status: str,
    result: str = "",
    execution_run_id: str = "",
) -> str:
    """
    Update the status of a step in the plan.
    Args:
        plan_id: The ID of the plan.
        step_id: The ID of the step.
        status: New status (pending, in_progress, completed, failed).
        result: Optional result description.
        execution_run_id: Optional ID of the current agent run executing this step.
    """
    # Removed invalid import from domain.planning.models
    from app.infrastructure.database.sql.database import session_scope

    # Use the shared models from infrastructure to match session definition
    from app.models import PlanStep

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


@evoloop_tool
async def analyze_feasibility(proposed_plan: str, config: RunnableConfig) -> str:
    """
    Analyze the technical feasibility of a proposed development plan.
    It retrieves relevant code context and checks for potential issues like hallucinations or breaking changes.
    Args:
        proposed_plan: The detailed plan step-by-step.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id or 1
    root = ctx.working_directory or "."

    try:
        from app.domain.codebase.retrieval.service import RetrievalService
        from app.infrastructure.config.service import SystemConfigService
        from app.infrastructure.llm.factory import get_default_llm

        # Retrieval
        retrieval_service = RetrievalService()
        search_results = await retrieval_service.search(proposed_plan, project_id=project_id, limit=5)

        context_str = "\n".join([f"File: {r['file_path']}\nSnippet: {r['content'][:500]}..." for r in search_results])

        # Get Project Structure
        # Use underlying Generator directly (no longer a tool)
        from app.domain.project.tree_generator import AnnotatedTreeGenerator

        # Smart Truncation enabled to avoid context overflow
        generator = AnnotatedTreeGenerator(root, max_depth=3, with_symbols=False, file_limit=30)
        tree = await generator.generate()

        # LLM Analysis
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        if not model_name:
            raise ValueError("LLM_MODEL not configured in SystemConfigService")
        llm = await get_default_llm(model_name=model_name)
        user_lang = SystemConfigService.get_language_preference()

        prompt_text = _render_analysis_prompt(
            plan=proposed_plan,
            context=context_str,
            tree=tree,
            user_lang=user_lang
        )
        
        # Use simple invoke with prepared text
        response = await llm.ainvoke(prompt_text, config=config)
        report = response.content if hasattr(response, 'content') else str(response)

        return report

    except Exception as e:
        logger.error(f"Feasibility analysis failed: {e}")
        return f"Analysis Failed: {str(e)}"
