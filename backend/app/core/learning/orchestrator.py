import logging
import json
from typing import Any

from app.core.events import system_bus
from app.core.events.registry import AgentEventType
from app.core.events.agent import AgentRunCompletedEvent
from app.core.engine.tasks import record_episode_task

logger = logging.getLogger(__name__)


class LearningOrchestrator:
    """
    Subscribes to agent execution events and triggers the learning pipeline (Episode recording -> Skill synthesis).
    
    This decouples the real-time agent execution from the background learning process.
    """

    @staticmethod
    async def on_agent_run_completed(event: AgentRunCompletedEvent) -> None:
        """
        Handler for AgentRunCompletedEvent.
        Checks if the run is eligible for learning and triggers the background task.
        """
        thread_id = event.thread_id
        project_id = event.project_id
        
        print(f"DEBUG: LearningOrchestrator received event for thread {thread_id}, status: {event.status}")
        
        if event.status != "done":
            logger.info(f"[Learning] Skipping run {thread_id}: status is {event.status}")
            return

        # 1. Check eligibility (to be expanded)
        logger.info(f"[Learning] 🚀 Triggering automated episode recording for thread: {thread_id}")

        try:
            print(f"DEBUG: LearningOrchestrator dispatching via celery_app.send_task(engine_record_episode)")
            from app.infrastructure.queue.celery import celery_app
            
            # Send task explicitly by name to ensure it reaches the correct broker/app
            task_res = celery_app.send_task(
                "engine_record_episode",
                kwargs={
                    "thread_id": thread_id,
                    "project_id": project_id,
                    "auto_synthesize": True
                },
                queue="default"
            )
            print(f"DEBUG: Task dispatched, task_id: {task_res.id}")
        except Exception as e:
            logger.error(f"[Learning] Failed to trigger recording task for {thread_id}: {e}")
            print(f"DEBUG: FAILED TO DISPATCH TASK: {e}")


def register_learning_handlers() -> None:
    """Register learning-related event handlers with the system bus."""
    system_bus.subscribe(AgentEventType.RUN_COMPLETED, LearningOrchestrator.on_agent_run_completed)
    logger.info("🧠 Learning Orchestrator registered (agent.run_completed -> Learning Pipeline)")
