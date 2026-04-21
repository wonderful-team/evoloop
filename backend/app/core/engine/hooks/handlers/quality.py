"""
Quality gate hook handler — blocks completion if checks fail.
"""

import logging

from app.core.engine.hooks.core import HookContext, HookResult

logger = logging.getLogger(__name__)


async def stop_quality_gate(context: HookContext) -> HookResult:
    """
    Quality gate at Stop event - can block completion if checks fail.

    This is where you can enforce:
    - All tests must pass
    - Code must be formatted
    - No TODOs left in code
    """
    blackboard = context.blackboard

    # Check if there were any failures in the session
    if getattr(blackboard, "test_failures", None) if blackboard else None:
        return HookResult(
            success=False,
            block=True,
            message="Tests failed. Please fix before completing.",
        )

    if getattr(blackboard, "lint_errors", None) if blackboard else None:
        return HookResult(
            success=False,
            block=True,
            message="Lint errors found. Please fix formatting.",
        )

    logger.debug("[Stop] Quality gate passed")
    return HookResult(success=True)
