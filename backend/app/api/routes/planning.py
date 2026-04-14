import logging

from fastapi import APIRouter
from sqlalchemy import select

from app.api.responses import BaseAPIResponse
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.planning import Plan, PlanStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations/{thread_id}/plan", tags=["planning"])


class PlanStepResponse(BaseAPIResponse):
    """Plan step item."""
    id: str
    title: str
    status: str
    result: str | None


class PlanDataResponse(DynamicBaseModel):
    """Nested plan data."""
    id: str
    title: str
    steps: list[PlanStepResponse]
    current_step_id: str | None


class PlanResponse(BaseAPIResponse):
    """Plan API response."""
    status: str
    plan: PlanDataResponse | None = None
    generated_at: str | None = None
    error: str | None = None


@router.get("", response_model=PlanResponse)
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
                return PlanResponse(status="no_plan", plan=None)

            # 2. Fetch Steps
            stmt_steps = select(PlanStep).where(PlanStep.plan_id == db_plan.id).order_by(PlanStep.order)
            res_steps = await session.execute(stmt_steps)
            steps = res_steps.scalars().all()

            # Find current step
            current_step = next((s for s in steps if s.status == "in_progress"), None)

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
        logger.error(f"Failed to get plan for {thread_id}: {e}")
        return PlanResponse(status="error", error=str(e))
