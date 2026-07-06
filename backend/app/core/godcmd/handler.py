"""
GodcmdHandler — intercepts #-prefixed messages and routes to commands.

Sits in the message pipeline before dispatch. If a message starts with `#`,
it extracts the command name + args, checks admin auth, and calls the
registered handler. The reply is published back to the same thread via
MessagePublisher.
"""

import logging
from typing import Any

from app.core.godcmd.auth import is_admin_user
from app.core.godcmd.registry import GodcmdContext, godcmd_registry

logger = logging.getLogger(__name__)

#: Prefix for godcmd commands
GODCMD_PREFIX = "#"


class GodcmdHandler:
    """
    Intercepts admin commands in chat messages.

    Usage (in the chat dispatch flow):
        handler = GodcmdHandler()
        if handler.is_godcmd(message):
            reply = await handler.handle(thread_id, message, user, project_id)
            # publish reply back to user, skip normal dispatch
    """

    def is_godcmd(self, message: str) -> bool:
        """Check if a message is a godcmd command (starts with #)."""
        return bool(message) and message.strip().startswith(GODCMD_PREFIX)

    async def handle(
        self,
        thread_id: str,
        message: str,
        user: Any = None,
        project_id: int | None = None,
    ) -> str:
        """
        Parse and execute a godcmd command.

        Args:
            thread_id: Current conversation thread
            message: Raw message text (e.g. "#stop thread-123")
            user: Authenticated User object
            project_id: Current project

        Returns:
            Text reply to send back to the user.
        """
        parts = message.strip()[len(GODCMD_PREFIX):].split()
        if not parts:
            return "Empty command. Use #help for available commands."

        cmd_name = parts[0].lower()
        args = parts[1:]

        cmd = godcmd_registry.get(cmd_name)
        if cmd is None:
            return f"Unknown command: #{cmd_name}. Use #help for available commands."

        if cmd.admin_only:
            admin = await is_admin_user(user)
            if not admin:
                member_id = getattr(user, "id", None) or getattr(user, "member_id", None)
                logger.warning("[Godcmd] Non-admin user %s attempted #%s", member_id, cmd_name)
                return f"Permission denied. #{cmd_name} requires admin access."

        ctx = GodcmdContext(
            thread_id=thread_id,
            project_id=project_id,
            user=user,
            member_id=getattr(user, "id", None) or getattr(user, "member_id", None),
            args=args,
            raw_message=message,
        )

        try:
            reply = await cmd.handler(ctx)
            logger.info("[Godcmd] #%s executed by %s on thread %s",
                        cmd_name, ctx.member_id, thread_id)
            return reply
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error("[Godcmd] #%s failed: %s", cmd_name, e)
            return f"Command #{cmd_name} failed: {e}"
