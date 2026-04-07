import logging

from app.core.events.decorators import event_register, event_subscribe
from app.core.engine.events import AgentEventType
from app.core.engine.events import AgentRunCompletedEvent

logger = logging.getLogger(__name__)


@event_register()
class LearningOrchestrator:
    """
    Subscribes to agent execution events and triggers the learning pipeline (Episode recording -> Skill synthesis).
    
    This decouples the real-time agent execution from the background learning process.
    """

    def __init__(self):
        pass

    @event_subscribe(AgentEventType.RUN_COMPLETED)
    async def on_agent_run_completed(self, event: AgentRunCompletedEvent) -> None:
        """
        Handler for AgentRunCompletedEvent.
        Checks if the run is eligible for learning and triggers the background task.
        """
        thread_id = event.thread_id
        project_id = event.project_id
        
        logger.debug(f"LearningOrchestrator received event for thread {thread_id}, status: {event.status}")
        
        if event.status != "done":
            logger.info(f"[Learning] Skipping run {thread_id}: status is {event.status}")
            return

        return


def register_learning_handlers() -> None:
    """
    Register learning-related event handlers with the system bus.
    
    Note: With @event_register() decorator, handlers are auto-registered on import.
    This function is kept for backward compatibility.
    """
    from app.core.execution.macro.advisor import register_self_healing_advisor

    # Instantiate to trigger auto-registration
    LearningOrchestrator()
    
    register_self_healing_advisor()
    logger.info("🧠 Learning Orchestrator & Self-Healing Advisor registered.")
