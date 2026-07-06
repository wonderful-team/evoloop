"""
Godcmd — in-conversation admin command channel.

Allows operators to manage the agent from chat (web/mobile) using
`#`-prefixed commands, similar to CowAgent's godcmd plugin.

Features:
- Auth-gated: only admin users (is_superuser or ADMIN_MEMBER_IDS config)
- Registered command pattern: @register_godcmd decorator + registry
- Built-in commands: #help, #status, #stop, #stopall, #config, #reload, #dream
- Audit log via activity_monitor.log_event
- Returns text reply through the normal message pipeline

Usage:
    # User sends "#status" in chat
    # GodcmdHandler intercepts, checks admin auth, routes to registered command
    # Command handler returns a text reply
    # Reply is published back to the same thread

    @register_godcmd("purge", description="Purge cache", admin_only=True)
    async def handle_purge(ctx: GodcmdContext) -> str:
        await clear_cache()
        return "Cache purged."
"""

from .auth import is_admin_user
from .commands import register_builtin_commands
from .handler import GodcmdHandler
from .registry import GodcmdContext, GodcmdRegistry, godcmd_registry, register_godcmd

__all__ = [
    "GodcmdRegistry",
    "godcmd_registry",
    "register_godcmd",
    "GodcmdContext",
    "GodcmdHandler",
    "is_admin_user",
    "register_builtin_commands",
]
