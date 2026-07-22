"""
Input channel base — IncomingMessage dataclass and InputChannel abstract class
are defined in ``app.core.channel.base`` to avoid circular imports.

This module re-exports them for convenience::

    from app.core.channel.input.base import IncomingMessage, InputChannel
"""

from app.core.channel.base import IncomingMessage, InputChannel

__all__ = ["IncomingMessage", "InputChannel"]
