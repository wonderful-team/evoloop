"""
Input channel abstraction — normalize source-specific raw messages
into ``IncomingMessage`` and dispatch through the agent engine.

Usage::

    from app.core.channel.input.voice_input import voice_input

    raw = {"thread_id": "...", "text": "..."}
    msg = await voice_input.receive(raw)
    if msg:
        result = await voice_input.dispatch(msg)
"""

from app.core.channel.base import IncomingMessage, InputChannel

__all__ = [
    "IncomingMessage",
    "InputChannel",
]
