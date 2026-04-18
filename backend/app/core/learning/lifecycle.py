"""
Learning Module Lifecycle Handlers
Handles application-level startup and session completion events for learning.
"""
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schema import SessionCompletedEvent

logger = logging.getLogger(__name__)


@event_register()
class LearningLifecycleHandler:
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

        # 2. Warm up caches
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
            )
            
            # Reconcile Skill
            if data.original_skill_id:
                logger.info(f"[Learning] 🔄 Triggering macro reconciliation for Skill {data.original_skill_id}")
                reconcile_skill_macro_task.delay(
                    skill_id=data.original_skill_id,
                    thread_id=data.thread_id
                )
        except Exception as e:
            logger.error(f"[Learning] Failed to trigger learning tasks: {e}")
