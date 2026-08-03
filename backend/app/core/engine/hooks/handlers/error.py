"""
Global error hook handler.
"""

import logging

from app.core.engine.hooks.core import HookContext, HookResult

logger = logging.getLogger(__name__)


async def error_handler(context: HookContext) -> HookResult:
    """
    Global error handling.

    Can be used for:
    - Error logging
    - Recovery attempts
    - Alerting
    """
    error = context.error
    error_message = str(error) if error else context.error_message or "Unknown error"

    logger.error(f"[ErrorHook] {error_message}")

    # Could send to error tracking service
    # Could attempt recovery
    # Could notify user

    return HookResult(success=True, data={"logged": True, "error": error_message})
