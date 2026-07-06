"""
GodcmdRegistry — registered command pattern for admin commands.

Commands are registered via the @register_godcmd decorator. Each command
has a name, handler, description, and admin_only flag. The handler receives
a GodcmdContext and returns a text reply.

Inspired by CowAgent's plugin registration + SystemConfigService's
register_change_handler pattern.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class GodcmdContext:
    """Context passed to a godcmd command handler."""
    thread_id: str
    project_id: int | None = None
    user: Any = None
    member_id: int | None = None
    args: list[str] = field(default_factory=list)
    raw_message: str = ""


@dataclass
class GodcmdCommand:
    """A registered godcmd command."""
    name: str
    handler: Callable[[GodcmdContext], Awaitable[str]]
    description: str = ""
    admin_only: bool = True
    aliases: list[str] = field(default_factory=list)


class GodcmdRegistry:
    """Registry of admin commands."""

    def __init__(self):
        self._commands: dict[str, GodcmdCommand] = {}

    def register(
        self,
        name: str,
        handler: Callable[[GodcmdContext], Awaitable[str]],
        description: str = "",
        admin_only: bool = True,
        aliases: list[str] | None = None,
    ) -> GodcmdCommand:
        """Register a godcmd command."""
        cmd = GodcmdCommand(
            name=name,
            handler=handler,
            description=description,
            admin_only=admin_only,
            aliases=aliases or [],
        )
        self._commands[name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd
        logger.info("[Godcmd] Registered command '%s' (admin_only=%s)", name, admin_only)
        return cmd

    def get(self, name: str) -> GodcmdCommand | None:
        """Get a command by name or alias."""
        return self._commands.get(name)

    def all_commands(self) -> list[GodcmdCommand]:
        """Get all unique commands (excluding aliases)."""
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return result

    def list_help(self) -> str:
        """Generate help text for all commands."""
        lines = ["Available admin commands:", ""]
        for cmd in sorted(self.all_commands(), key=lambda c: c.name):
            alias_str = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  #{cmd.name}{alias_str} — {cmd.description}")
        return "\n".join(lines)


#: Global singleton
godcmd_registry = GodcmdRegistry()


def register_godcmd(
    name: str,
    description: str = "",
    admin_only: bool = True,
    aliases: list[str] | None = None,
):
    """Decorator to register a godcmd command handler."""
    def decorator(handler: Callable[[GodcmdContext], Awaitable[str]]):
        godcmd_registry.register(
            name=name,
            handler=handler,
            description=description,
            admin_only=admin_only,
            aliases=aliases,
        )
        return handler
    return decorator
