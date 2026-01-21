from fastapi import APIRouter
from sqlalchemy import select

from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.planning import Plan, PlanStep
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations/{thread_id}/plan", tags=["planning"])


@router.get("")
async def get_plan(thread_id: str):
    """
    Get the current active execution plan for the thread from the Database.
    Targeting persistent storage instead of transient AgentState.
    """
    try:
        async with session_scope() as session:
            # 1. Fetch Active Plan
            stmt = select(Plan).where(Plan.thread_id == thread_id, Plan.status == "active")
            res = await session.execute(stmt)
            db_plan = res.scalars().first()

            if not db_plan:
                # If no active plan, check for completed ones?
                # For now, just return "no_graph" equivalent or "no_plan"
                return {"status": "no_plan", "plan": None}

            # 2. Fetch Steps
            stmt_steps = select(PlanStep).where(PlanStep.plan_id == db_plan.id).order_by(PlanStep.order)
            res_steps = await session.execute(stmt_steps)
            steps = res_steps.scalars().all()

            # 3. Construct Response
            plan_data = {
                "id": db_plan.id,
                "title": db_plan.title,
                "steps": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "status": s.status,
                        "result": s.result,  # Optional field for step output summary
                        # "execution_run_id": s.execution_run_id # If we have this linkage
                    } for s in steps
                ],
                "current_step_id": None,
            }

            # Find current step
            current_step = next((s for s in steps if s.status == "in_progress"), None)
            if current_step:
                plan_data["current_step_id"] = current_step.id

            return {
                "status": "success",
                "plan": plan_data,  # Frontend expects this nested 'plan' object
                "generated_at": db_plan.created_at.isoformat() if db_plan.created_at else None,
            }

    except Exception as e:
        logger.error(f"Failed to get plan for {thread_id}: {e}")
        return {"status": "error", "error": str(e)}
