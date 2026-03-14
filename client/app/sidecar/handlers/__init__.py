"""
Sidecar message handlers.

Registers all handlers for the Sidecar protocol.
"""

from . import tools
from . import events
from . import system


def register_all_handlers(protocol):
    """Register all handlers with the protocol instance."""
    # Tool execution handlers
    protocol.register_handler("execute", tools.handle_execute)
    protocol.register_handler("ping", tools.handle_ping)

    # System handlers
    protocol.register_handler("init", system.handle_init)
    protocol.register_handler("shutdown", system.handle_shutdown)
    protocol.register_handler("status", system.handle_status)

    # Events are sent from Client to Tauri, no handlers needed
