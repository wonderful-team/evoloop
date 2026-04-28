import logging

from sqlalchemy import or_, select

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoItem, TodoPriority, TodoStatus

logger = logging.getLogger(__name__)


class ProjectContextPlugin(ContextPlugin):
    """
    Hydrates the EvoContext with project-specific database state:
    - Active Plans
    - High-priority or In-Progress Todos
    """

    def hydrate(self, ctx: EvoContext) -> None:
        if not ctx.project_id:
            return

        try:
            with session_scope() as session:
                todos = session.execute(
                    select(TodoItem).where(
                        TodoItem.project_id == ctx.project_id,
                        TodoItem.status == TodoStatus.PENDING,
                        or_(
                            TodoItem.priority == TodoPriority.HIGH,
                            TodoItem.priority == TodoPriority.MEDIUM,
                        ),
                    )
                ).scalars().all()

                # Fetch Active Plan if thread exists
                active_plan = None
                if ctx.thread_id:
                    from app.models.planning import Plan, PlanStep
                    stmt = select(Plan).where(Plan.thread_id == ctx.thread_id, Plan.status == "active")
                    res = session.execute(stmt)
                    db_plan = res.scalars().first()

                    if db_plan:
                        stmt_steps = select(PlanStep).where(PlanStep.plan_id == db_plan.id).order_by(PlanStep.order)
                        res_steps = session.execute(stmt_steps)
                        steps = res_steps.scalars().all()

                        steps_str = ""
                        active_step_found = False
                        for s in steps:
                            marker = "[ ]"
                            if s.status == "completed":
                                marker = "[x]"
                            elif s.status == "in_progress":
                                marker = "[>] (CURRENT)"
                            elif s.status == "failed":
                                marker = "[!]"

                            steps_str += f"\n{marker} {s.title}"
                            if s.status == "in_progress":
                                active_step_found = True

                        active_plan_context = f"PLAN: {db_plan.title}\nSTEPS:{steps_str}"
                        if active_step_found:
                            active_plan_context += "\n\n-> FOCUS: Execute the [>] CURRENT step."
                        else:
                            active_plan_context += "\n\n-> ACTION: Mark the next step as in_progress."

                        ctx.metadata.active_plan_context = active_plan_context

        except Exception as e:
            logger.error(f"[ProjectContextPlugin] Failed to fetch context from DB: {e}")


