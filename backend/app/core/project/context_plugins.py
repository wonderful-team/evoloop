"""
ProjectStateContextPlugin — hydrates EvoContext with project DB state.

Renames the duplicate ProjectContextPlugin (which conflicts with
context_plugin.py) to ProjectStateContextPlugin. Fixes the sync/async
bug where session_scope (an asynccontextmanager) was used with `with`
instead of `async with`.
"""

import logging

from sqlalchemy import select

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.core.routing.constants import INTENT_DIRECT_ANSWER, INTENT_ENVIRONMENT_QUERY
from app.infrastructure.database import sync_session_scope

logger = logging.getLogger(__name__)


class ProjectStateContextPlugin(ContextPlugin):
    """
    Hydrates the EvoContext with project-specific database state:
    - Active Plans (with step status + FOCUS directive)
    """

    _SKIP_FOR_INTENTS: frozenset[str | None] = frozenset(
        {INTENT_DIRECT_ANSWER, INTENT_ENVIRONMENT_QUERY}
    )

    def is_needed(self, intent: str | None) -> bool:
        """Project state is not needed for greetings or raw environment questions."""
        return intent not in self._SKIP_FOR_INTENTS

    def hydrate(self, ctx: EvoContext) -> None:
        if not ctx.project_id:
            return

        try:
            with sync_session_scope() as session:
                if ctx.thread_id:
                    from app.domain.planning.constants import (
                        PlanStatus,
                        PlanStepStatus,
                    )
                    from app.models.planning import Plan, PlanStep

                    stmt = select(Plan).where(
                        Plan.thread_id == ctx.thread_id,
                        Plan.status == PlanStatus.ACTIVE.value,
                    )
                    res = session.execute(stmt)
                    db_plan = res.scalars().first()

                    if db_plan:
                        stmt_steps = (
                            select(PlanStep)
                            .where(PlanStep.plan_id == db_plan.id)
                            .order_by(PlanStep.order)
                        )
                        res_steps = session.execute(stmt_steps)
                        steps = res_steps.scalars().all()

                        steps_str = ""
                        active_step_found = False
                        for s in steps:
                            marker = "[ ]"
                            if s.status == PlanStepStatus.COMPLETED.value:
                                marker = "[x]"
                            elif s.status == PlanStepStatus.IN_PROGRESS.value:
                                marker = "[>] (CURRENT)"
                            elif s.status == PlanStepStatus.FAILED.value:
                                marker = "[!]"

                            steps_str += f"\n{marker} {s.title}"
                            if s.status == PlanStepStatus.IN_PROGRESS.value:
                                active_step_found = True

                        active_plan_context = (
                            f"PLAN: {db_plan.title}\nSTEPS:{steps_str}"
                        )
                        if active_step_found:
                            active_plan_context += (
                                "\n\n-> FOCUS: Execute the [>] CURRENT step."
                            )
                        else:
                            active_plan_context += (
                                "\n\n-> ACTION: Mark the next step as in_progress."
                            )

                        ctx.metadata.active_plan_context = active_plan_context

        except Exception:
            logger.exception(
                "[ProjectStateContextPlugin] Failed to fetch context from DB"
            )


plugin_registry.register(ProjectStateContextPlugin())
