"""
Macro Self-Healing Advisor
==========================

Event-driven advisor that suggests self-healing actions when macro execution fails.

This module provides decoupled listening for macro failures and generates
contextual recovery suggestions based on the SelfHealingPolicy.

Usage:
    The advisor is auto-registered via @event_register() decorator.
    It listens to MacroEventType.EXECUTION_FAILED events and appends
    suggestions to the event for the agent to act upon.
"""

import logging

from app.core.events.decorators import event_register, event_subscribe
from app.core.execution.macro.events import MacroEventType, MacroExecutionFailedEvent
from app.core.execution.macro.healing_policy import SelfHealingPolicy

logger = logging.getLogger(__name__)


@event_register()
class MacroSelfHealingAdvisor:
    """
    Decoupled listener that decides if an agent should attempt self-healing
    after a macro fails.
    
    This advisor uses the centralized SelfHealingPolicy for consistency,
    but adds contextual suggestions based on the failure context.
    """

    def __init__(self):
        pass

    @event_subscribe(MacroEventType.EXECUTION_FAILED)
    async def on_macro_failed(self, event: MacroExecutionFailedEvent) -> None:
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
    """
    Register the advisor with the system bus.
    
    Note: With @event_register() decorator, handlers are auto-registered on import.
    This function is kept for explicit registration if needed.
    """
    # Instantiate to trigger auto-registration
    MacroSelfHealingAdvisor()
    logger.info("🩺 Macro Self-Healing Advisor registered.")
