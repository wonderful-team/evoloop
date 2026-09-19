import logging

from fastapi import APIRouter
from sqlalchemy import select

from app.api.schemas.planning import PlanDataResponse, PlanResponse, PlanStepResponse
from app.domain.planning.constants import PlanStepStatus
from app.infrastructure.database import session_scope
from app.models.planning import Plan, PlanStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations/{thread_id}/plan", tags=["planning"])


@router.get("", response_model=PlanResponse)
async def get_plan(thread_id: str):
    """
    Get the current active execution plan for the thread from the Database.
    Targeting persistent storage instead of transient AgentState.
    """
    try:
        async with session_scope() as session:
            # 1. Fetch the latest plan. Workflow plans intentionally become
            # completed when their task reaches a terminal state; those plans
            # must remain observable in the duty workbench.
            stmt = select(Plan).where(
                Plan.thread_id == thread_id
            )
            res = await session.execute(stmt)
            db_plan = res.scalars().first()

            if not db_plan:
                # If no active plan, check for completed ones?
                # For now, just return "no_graph" equivalent or "no_plan"
                return PlanResponse(status="no_plan", plan=None)

            # 2. Fetch Steps
            stmt_steps = select(PlanStep).where(PlanStep.plan_id == db_plan.id).order_by(PlanStep.order)
            res_steps = await session.execute(stmt_steps)
            steps = res_steps.scalars().all()

            # Find current step
            current_step = next(
                (s for s in steps if s.status == PlanStepStatus.IN_PROGRESS.value),
                None,
            )

            plan_data = PlanDataResponse(
                id=db_plan.id,
                title=db_plan.title,
                steps=[
                    PlanStepResponse(
                        id=s.id,
                        title=s.title,
                        status=s.status,
                        result=s.result,
                    ) for s in steps
                ],
                current_step_id=current_step.id if current_step else None,
            )

            return PlanResponse(
                status="success",
                plan=plan_data,
                generated_at=db_plan.created_at.isoformat() if db_plan.created_at else None,
            )

    except Exception as e:
        logger.exception(f"Failed to get plan for {thread_id}: {e}")
        return PlanResponse(status="error", error=str(e))
