"""
Self-Healing Policy - Unified self-healing decision logic

This module provides a centralized, consistent way to determine if self-healing
should be allowed for macro execution failures.

Decision hierarchy (all must be True for healing to be allowed):
1. Global config: ENABLE_MACRO_SELF_HEALING
2. Macro-level: macro.allow_self_healing
3. Execution-level: execution_params.get("_allow_self_healing", True)

Usage:
    from app.core.learning.macro.healing_policy import SelfHealingPolicy

    # Check if healing is allowed
    if SelfHealingPolicy.is_allowed(macro=macro, execution_params=params):
        # Attempt self-healing

    # Or get detailed decision info
    decision = SelfHealingPolicy.check(macro=macro, execution_params=params)
    if not decision.allowed:
        logger.info(f"Self-healing disabled: {decision.reason}")
"""

from typing import Any

from app.core.config import settings
from app.core.learning.macro.schemas import HealingDecision
from app.models.macro import Macro


class SelfHealingPolicy:
    """
    Centralized self-healing policy enforcement.

    All self-healing decisions should go through this class to ensure
    consistent behavior across the codebase.
    """

    @classmethod
    def check(
        cls,
        macro: "Macro | None" = None,
        execution_params: dict[str, Any] | None = None,
    ) -> HealingDecision:
        """
        Check if self-healing is allowed based on all policy levels.

        Args:
            macro: The Macro being executed (optional)
            execution_params: Execution-time parameters (optional)

        Returns:
            HealingDecision with allowed flag, reason, and source
        """
        # Level 1: Global config
        if not settings.ENABLE_MACRO_SELF_HEALING:
            return HealingDecision(
                allowed=False,
                reason="Global policy disables macro self-healing",
                source="global",
            )

        # Level 2: Macro-level switch
        if macro is not None and not macro.allow_self_healing:
            return HealingDecision(
                allowed=False,
                reason=f"Macro '{macro.name}' has self-healing disabled",
                source="macro",
            )

        # Level 3: Execution-time override
        exec_params = execution_params or {}
        # Support both key formats for backward compatibility
        allow_healing = exec_params.get("_allow_self_healing", True)

        if not allow_healing:
            return HealingDecision(
                allowed=False,
                reason="Execution explicitly disabled self-healing",
                source="execution",
            )

        # All checks passed
        return HealingDecision(
            allowed=True, reason="Self-healing is enabled", source="allowed"
        )

    @classmethod
    def is_allowed(
        cls,
        macro: "Macro | None" = None,
        execution_params: dict[str, Any] | None = None,
    ) -> bool:
        """
        Simple boolean check if self-healing is allowed.

        Args:
            macro: The Macro being executed (optional)
            execution_params: Execution-time parameters (optional)

        Returns:
            True if self-healing is allowed, False otherwise
        """
        return cls.check(macro, execution_params).allowed

    @classmethod
    def get_disabled_message(cls, decision: HealingDecision) -> str:
        """
        Get a user-friendly message explaining why self-healing is disabled.

        Args:
            decision: A HealingDecision where allowed=False

        Returns:
            Human-readable explanation message
        """
        if decision.allowed:
            return ""

        messages = {
            "global": (
                "[SELF_HEALING_DISABLED] Global policy prevents automatic recovery. "
                "The agent should NOT attempt to heal this macro."
            ),
            "macro": (
                f"[SELF_HEALING_DISABLED] This macro has self-healing disabled: {decision.reason}. "
                "The agent should NOT attempt to heal this macro."
            ),
            "execution": (
                "[SELF_HEALING_DISABLED] This specific execution task requested no automatic recovery."
            ),
        }

        return messages.get(
            decision.source, f"[SELF_HEALING_DISABLED] {decision.reason}"
        )

    @classmethod
    def get_enabled_message(
        cls, macro_name: str | None = None, error_message: str | None = None
    ) -> str:
        """
        Get a user-friendly message suggesting self-healing recovery.

        Args:
            macro_name: Name of the failed macro
            error_message: The error that caused the failure

        Returns:
            Human-readable recovery suggestion
        """
        base_msg = (
            "[HINT] Macro step failed. "
            "Since perceptual self-healing is enabled, you should now attempt to recover manually "
            "using basic tools (browser, desktop, etc.) to complete the mission. "
            "After successful recovery, you may call `reconcile_skill` to fix this macro permanently."
        )

        if macro_name and error_message:
            return (
                f"[HINT] Macro '{macro_name}' failed: {error_message}. " + base_msg[7:]
            )  # Remove the tag from base

        return base_msg
