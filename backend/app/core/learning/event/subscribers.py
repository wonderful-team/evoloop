"""
Learning Module Event Subscribers
==================================

Handles application-level startup, session completion, and rewind cleanup
for the learning domain.
"""
import logging

from sqlalchemy import delete, select

from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe, register_instance_handlers
from app.core.events.schemas import SessionCompletedEvent
from app.core.learning.event.schemas import TraceCleanupEvent
from app.core.learning.skill_sync_service import skill_sync_service
from app.infrastructure.database.sql.database import session_scope
from app.models import Message

logger = logging.getLogger(__name__)


@event_register()
class LearningLifecycleSubscriber:
    """
    Handles application-level lifecycle events for the Learning domain.
    
    Includes:
    - Skill synchronization and warming on app start
    - Episode recording and skill reconciliation on session completion
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED event:
        1. Sync system skills from filesystem to DB
        2. Warm up skills discovery cache
        3. Warm up user preferences
        """
        from app.core.learning.discovery import skill_discovery
        
        # 1. Sync system skills
        try:
            logger.info("[Learning] 📚 Synchronizing system skills...")
            await skill_discovery._sync_system_skills()
            logger.info("[Learning] ✓ System skills synchronized")
        except Exception as e:
            logger.warning(f"[Learning] Skill synchronization failed: {e}")

        # 2. Start skills file watcher
        try:
            from app.core.learning.skill_file_watcher import skills_file_watcher
            skills_file_watcher.start()
            logger.info("[Learning] ✓ Skills file watcher started")
        except Exception as e:
            logger.warning(f"[Learning] Failed to start skills file watcher: {e}")

        # 3. Warm up caches
        try:
            skills = await skill_discovery.get_active_skills_list()
            logger.info(f"[Learning] ✓ Skills cache warmed: {len(skills)} skills")
        except Exception as e:
            logger.warning(f"[Learning] Skills cache warming failed: {e}")

        # 3. User preferences
        try:
            from app.infrastructure.config.service import SystemConfigService
            lang_pref = SystemConfigService.get_language_preference()
            logger.info(f"[Learning] ✓ User preferences cached: language={lang_pref}")
        except Exception as e:
            logger.warning(f"[Learning] User preferences caching failed: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_app_stopping(self, event):
        """Stop the skills file watcher on shutdown."""
        from app.core.learning.skill_file_watcher import skills_file_watcher
        skills_file_watcher.stop()

    @event_subscribe(SystemEventType.SKILL_CREATED)
    async def on_skill_created(self, event):
        """Handle SKILL_CREATED: export skill to filesystem."""
        data = event.data
        await skill_sync_service.export_skill_to_file(data["skill_id"])

    @event_subscribe(SystemEventType.SKILL_UPDATED)
    async def on_skill_updated(self, event):
        """Handle SKILL_UPDATED: export updated skill to filesystem."""
        data = event.data
        await skill_sync_service.export_skill_to_file(data["skill_id"])

    @event_subscribe(SystemEventType.SKILL_DELETED)
    async def on_skill_deleted(self, event):
        """Handle SKILL_DELETED: remove skill file from filesystem."""
        data = event.data
        await skill_sync_service.delete_skill_file(
            skill_id=data["skill_id"],
            namespace=data.get("namespace"),
            name=data.get("name"),
        )

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Record episode and reconcile skills when a session completes successfully.
        """
        data = event.data
        logger.info(f"[Learning] 🎓 Session completed for thread {data.thread_id}. Recording experience...")

        try:
            from app.core.engine.tasks import record_episode_task, reconcile_skill_macro_task
            
            # Record Episode (experience)
            record_episode_task.delay(
                thread_id=data.thread_id,
                project_id=data.project_id,
                goal=data.ticket_topic or "[Auto-recorded]",
                result_summary=data.summary,
                concept_names=[],
                source_message_id=data.run_id or data.thread_id,
                model=data.model,
            )
            
            # Reconcile Skill
            if data.original_skill_id:
                logger.info(f"[Learning] 🔄 Triggering macro reconciliation for Skill {data.original_skill_id}")
                reconcile_skill_macro_task.delay(
                    skill_id=data.original_skill_id,
                    thread_id=data.thread_id,
                    model=data.model,
                )
        except Exception as e:
            logger.error(f"[Learning] Failed to trigger learning tasks: {e}")


@event_register()
class TraceRewind:
    """Event-driven trace event cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "TraceRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare trace cleanup.
        
        Extracts message IDs and publishes a TRACE_CLEANUP event.
        """
        # Use pre-computed database IDs if available, otherwise fall back to query
        message_ids = event.affected_message_ids or await self._find_message_ids(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target
        )

        if message_ids or event.affected_run_ids:
            count = await self._delete_traces(
                source_message_ids=message_ids,
                run_ids=event.affected_run_ids
            )
            self._deleted_count = count
            event.results["traces"] = count

            from app.core.learning.event.publishers import publish_trace_cleanup
            await publish_trace_cleanup(
                thread_id=event.thread_id,
                source_message_ids=message_ids,
                affected_run_ids=event.affected_run_ids
            )
            logger.info(f"[TraceRewind] Deleted {count} trace events for thread {event.thread_id}")
        else:
            logger.debug(f"[TraceRewind] No trace events found to delete for thread {event.thread_id}")

    @event_subscribe(RewindEventType.TRACE_CLEANUP)
    async def _handle_trace_cleanup(self, event: "TraceCleanupEvent") -> None:
        """
        Handle specific trace cleanup event.
        
        This performs the actual trace event deletion.
        """
        try:
            count = await self._delete_traces(
                source_message_ids=event.source_message_ids,
                run_ids=event.affected_run_ids
            )
            self._deleted_count = count
            logger.info(f"[TraceRewind] Deleted {count} trace events")
        except Exception as e:
            logger.error(f"[TraceRewind] Trace cleanup failed: {e}")
            raise

    async def _find_message_ids(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """Find message IDs to clean up for the given thread."""
        from app.models import Message

        async with session_scope() as session:
            stmt = select(Message.id).where(Message.thread_id == thread_id)

            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(Message.id == target_message_id)
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()
                
                if target_seq is None:
                    logger.warning(f"[TraceRewind] Target message {target_message_id} not found")
                    return []

                if include_target:
                    stmt = stmt.where(Message.sequence_number >= target_seq)
                else:
                    stmt = stmt.where(Message.sequence_number > target_seq)

            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_traces(
        self,
        source_message_ids: list[str],
        run_ids: list[str] | None = None
    ) -> int:
        """
        Delete trace events by message IDs or run IDs.
        """
        from app.models.learning import TraceEvent

        final_run_ids = list(run_ids or [])

        async with session_scope() as session:
            # If no run_ids but we have message_ids, resolve them
            if not final_run_ids and source_message_ids:
                stmt_msg = select(Message.run_id).where(Message.id.in_(source_message_ids))
                res_msg = await session.execute(stmt_msg)
                final_run_ids = [r[0] for r in res_msg.all() if r[0]]
            
            if not final_run_ids:
                return 0

            # Perform deletion by run_id
            stmt = delete(TraceEvent).where(TraceEvent.run_id.in_(final_run_ids))
            result = await session.execute(stmt)
            count = result.rowcount
            logger.info(f"[TraceRewind] Deleted {count} trace events for {len(final_run_ids)} runs")
            return count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_traces(message_ids)

    def get_deleted_count(self) -> int:
        """Get the count of trace events deleted in the last operation."""
        return self._deleted_count
