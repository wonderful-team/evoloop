import logging
from app.core.events import system_bus, MacroEventType
from app.core.events.macro import MacroExecutionFailedEvent
from app.core.config import settings

logger = logging.getLogger(__name__)


class MacroSelfHealingAdvisor:
    """
    Decoupled listener that decides if an agent should attempt self-healing
    after a macro fails.
    """

    @staticmethod
    async def on_macro_failed(event: MacroExecutionFailedEvent) -> None:
        """
        Evaluate healing switches and append guidance to the event.
        """
        # 1. Global Switch
        if not settings.ENABLE_MACRO_SELF_HEALING:
            logger.info(f"[Self-Healing] Global skip for macro failure in thread {event.thread_id}")
            event.suggestions.append(
                "⚠️ [SELF_HEALING_DISABLED] Global policy prevents automatic recovery. "
                "The agent should NOT attempt to heal this macro."
            )
            return

        # 2. Call-level Switch
        allow_call_healing = event.data.get("allow_self_healing", True)
        if not allow_call_healing:
            logger.info(f"[Self-Healing] Call-level skip for macro failure in thread {event.thread_id}")
            event.suggestions.append(
                "⚠️ [SELF_HEALING_DISABLED] This specific execution task requested no automatic recovery."
            )
            return

        # 3. Path-based or Level-based heuristics can go here
        
        # 4. Success Case: Suggest recovery
        logger.info(f"[Self-Healing] Suggesting perceptual recovery for macro '{event.skill_name}'")
        event.suggestions.append(
            f"💡 Macro step failed: {event.error_message}. "
            "Since perceptual self-healing is enabled, you should now attempt to recover manually "
            "using basic tools (browser_control, desktop_control, etc.) to complete the mission. "
            "After successful recovery, you may call `reconcile_skill` to fix this macro permanently."
        )


def register_self_healing_advisor():
    """Register the advisor with the system bus."""
    system_bus.subscribe(MacroEventType.EXECUTION_FAILED, MacroSelfHealingAdvisor.on_macro_failed)
    logger.info("🩺 Macro Self-Healing Advisor registered.")
