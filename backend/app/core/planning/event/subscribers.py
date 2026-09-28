"""
Planning Event Subscribers
==========================

Handles plan lifecycle events, including rewind cleanup.
"""

import logging

from sqlalchemy import select

from app.core.engine.rewind import REWIND_REQUESTED, RewindRequestedEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.planning.constants import PlanStatus, PlanStepStatus
from app.core.planning.event import PlanUpdatedEvent
from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)


@event_register()
class PlanRewind:
    """Event-driven plan cleanup handler for rewind operations.

    On rewind, resets PlanStep statuses that were affected by the deleted
    messages, or deletes the entire Plan if it was created after the rewind
    point.
    """

    def __init__(self):
        self._reset_count = 0

    @event_subscribe(REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        publish_event = None
        try:
            async with session_scope() as session:
                # Step 1: resolve target message timestamp
                target_created_at = await self._get_target_created_at(
                    session, event.thread_id, event.target_sequence
                )

                # Step 1: load plan for the thread
                from app.models.planning import Plan as DBPlan
                from app.models.planning import PlanStep as DBPlanStep

                stmt = select(DBPlan).where(DBPlan.thread_id == event.thread_id)
                result = await session.execute(stmt)
                plan = result.scalar_one_or_none()
                if not plan:
                    return

                # Step 3: if the plan was created after the rewind point,
                # it should not exist yet → delete entirely
                if (
                    target_created_at is not None
                    and plan.created_at >= target_created_at
                ):
                    await session.delete(plan)
                    self._reset_count = 1
                    event.results["plans"] = 1
                    logger.info(
                        "[PlanRewind] Deleted plan %s for thread %s "
                        "(created after rewind point)",
                        plan.id,
                        event.thread_id,
                    )
                    publish_event = PlanUpdatedEvent(
                        thread_id=event.thread_id,
                        plan_id=plan.id,
                        status=PlanStepStatus.DELETED.value,
                    )
                    return

                # Step 4: load steps and determine which are stale
                stmt_steps = (
                    select(DBPlanStep)
                    .where(DBPlanStep.plan_id == plan.id)
                    .order_by(DBPlanStep.order)
                )
                result_steps = await session.execute(stmt_steps)
                steps = result_steps.scalars().all()

                affected_run_ids = set(event.affected_run_ids or [])
                reset_count = 0

                for step in steps:
                    if self._is_step_stale(step, affected_run_ids, target_created_at):
                        self._reset_step(step)
                        reset_count += 1

                if reset_count > 0:
                    plan.status = PlanStatus.ACTIVE.value
                    # Set the first non-completed step to in_progress
                    for s in steps:
                        if s.status != PlanStepStatus.COMPLETED.value:
                            s.status = PlanStepStatus.IN_PROGRESS.value
                            break

                self._reset_count = reset_count
                event.results["plans"] = reset_count

                if reset_count > 0:
                    logger.info(
                        "[PlanRewind] Reset %d steps for plan %s in thread %s",
                        reset_count,
                        plan.id,
                        event.thread_id,
                    )
                    publish_event = PlanUpdatedEvent(
                        thread_id=event.thread_id, plan_id=plan.id
                    )
                else:
                    logger.debug(
                        "[PlanRewind] No stale steps for plan %s in thread %s",
                        plan.id,
                        event.thread_id,
                    )

            # Notify frontend plan panel to refresh **outside** the DB session
            # so the connection is returned to the pool before doing IO.
            if publish_event:
                try:
                    from app.core.events import system_bus

                    await system_bus.publish(publish_event)
                except Exception as e:
                    logger.warning(
                        "[PlanRewind] Failed to publish plan updated event: %s",
                        e,
                    )
        except Exception as e:
            logger.error("[PlanRewind] Plan cleanup failed: %s", e)
            event.errors.append(str(e))
            event.success = False

    async def _get_target_created_at(
        self, session, thread_id: str, target_sequence: int
    ) -> object | None:
        """Return the created_at timestamp of the target message, or None."""
        if target_sequence <= 0:
            return None
        from app.models import Message

        stmt = select(Message.created_at).where(
            Message.thread_id == thread_id,
            Message.sequence_number == target_sequence,
        )
        return await session.scalar(stmt)

    def _is_step_stale(
        self,
        step,
        affected_run_ids: set[str],
        target_created_at: object | None,
    ) -> bool:
        """Decide whether a PlanStep was affected by the rewind.

        A step is stale when:
        - It has an execution_run_id that is in the affected set, OR
        - It has no execution_run_id but its updated_at is >= the target
          message timestamp (meaning its status was auto-advanced during
          the deleted timeline).
        """
        if step.execution_run_id and step.execution_run_id in affected_run_ids:
            return True
        if (
            step.execution_run_id is None
            and target_created_at is not None
            and step.updated_at is not None
            and step.updated_at >= target_created_at
        ):
            return True
        return False

    def _reset_step(self, step) -> None:
        """Reset a PlanStep to its initial state."""
        step.execution_run_id = None
        step.result = None
        step.status = PlanStepStatus.PENDING.value

    async def cleanup(self, thread_id: str, **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        from app.models.planning import Plan as DBPlan
        from app.models.planning import PlanStep as DBPlanStep

        async with session_scope() as session:
            stmt = select(DBPlan).where(DBPlan.thread_id == thread_id)
            result = await session.execute(stmt)
            plan = result.scalar_one_or_none()
            if not plan:
                return 0

            stmt_steps = (
                select(DBPlanStep)
                .where(DBPlanStep.plan_id == plan.id)
                .order_by(DBPlanStep.order)
            )
            result_steps = await session.execute(stmt_steps)
            steps = result_steps.scalars().all()

            for step in steps:
                self._reset_step(step)
            if steps:
                steps[0].status = PlanStepStatus.IN_PROGRESS.value
            plan.status = PlanStatus.ACTIVE.value
            return len(steps)
