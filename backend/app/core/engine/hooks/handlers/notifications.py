"""
Notification hook handler.
"""

import logging

from app.core.engine.hooks.core import HookContext, HookResult

logger = logging.getLogger(__name__)


async def notification_handler(context: HookContext) -> HookResult:
    """
    Handle system notifications.

    Can be used for:
    - Desktop notifications
    - Slack/Teams alerts
    - Email notifications
    - Sound alerts (TTS)
    """
    message = context.metadata.get("message", "")
    notification_type = context.metadata.get("type", "info")

    logger.info(f"[Notification] {notification_type}: {message}")

    # Example: Desktop notification (macOS)
    # import subprocess
    # subprocess.run([
    #     "osascript", "-e",
    #     f'display notification "{message}" with title "EvoLoop"'
    # ])

    return HookResult(
        success=True,
        data={"notified": True, "type": notification_type}
    )
