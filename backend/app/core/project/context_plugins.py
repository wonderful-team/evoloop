"""
ProjectStateContextPlugin — hydrates EvoContext with project DB state.

Renames the duplicate ProjectContextPlugin (which conflicts with
context_plugin.py) to ProjectStateContextPlugin. Fixes the sync/async
bug where session_scope (an asynccontextmanager) was used with `with`
instead of `async with`.
"""
import logging

from sqlalchemy import or_, select

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.infrastructure.database import sync_session_scope
from app.models.todo import TodoItem, TodoPriority, TodoStatus

logger = logging.getLogger(__name__)


class ProjectStateContextPlugin(ContextPlugin):
    """
    Hydrates the EvoContext with project-specific database state:
    - Active Plans
    - High-priority or In-Progress Todos
    """

    def hydrate(self, ctx: EvoContext) -> None:
        if not ctx.project_id:
            return

        try:
            with sync_session_scope() as session:
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

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[ProjectStateContextPlugin] Failed to fetch context from DB: {e}")


plugin_registry.register(ProjectStateContextPlugin())
