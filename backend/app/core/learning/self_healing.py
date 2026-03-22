import logging
from app.core.events import system_bus, MacroEventType
from app.core.events.macro import MacroExecutionFailedEvent
from app.core.execution.macro.healing_policy import SelfHealingPolicy

logger = logging.getLogger(__name__)


class MacroSelfHealingAdvisor:
    """
    Decoupled listener that decides if an agent should attempt self-healing
    after a macro fails.
    
    This advisor uses the centralized SelfHealingPolicy for consistency,
    but adds contextual suggestions based on the failure context.
    """

    @staticmethod
    async def on_macro_failed(event: MacroExecutionFailedEvent) -> None:
        """
        Evaluate healing switches and append guidance to the event.
        Uses centralized SelfHealingPolicy for decision making.
        """
        # Use centralized policy check
        decision = SelfHealingPolicy.check(
            skill=None,  # Skill-level check already done in MacroService
            execution_params=event.data
        )
        
        if not decision.allowed:
            logger.info(f"[Self-Healing] {decision.source}-level skip for macro failure in thread {event.thread_id}")
            event.suggestions.append(
                SelfHealingPolicy.get_disabled_message(decision)
            )
            return

        # Success Case: Suggest recovery with contextual information
        logger.info(f"[Self-Healing] Suggesting perceptual recovery for macro '{event.skill_name}'")
        event.suggestions.append(
            SelfHealingPolicy.get_enabled_message(
                skill_name=event.skill_name,
                error_message=event.error_message
            )
        )


def register_self_healing_advisor():
    """Register the advisor with the system bus."""
    system_bus.subscribe(MacroEventType.EXECUTION_FAILED, MacroSelfHealingAdvisor.on_macro_failed)
    logger.info("🩺 Macro Self-Healing Advisor registered.")
