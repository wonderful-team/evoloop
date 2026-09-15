"""
Channel abstraction — unified interface for message intake and delivery.

- ``input/`` — InputChannel subclasses that normalize source-specific raw
  messages (voice, mobile, web) into a common ``IncomingMessage``.
- ``output/`` — Channel subclasses that deliver agent results to external
  transports (voice WS, SSE, mobile push, etc.).
"""

from .base import (
    Channel,
    ChannelContext,
    IncomingMessage,
    InputChannel,
)
from .input.mcp_message import McpMessageChannel
from .input.mobile_input import mobile_input
from .input.voice_input import voice_input
from .input.web_input import web_input
from .output.mobile_channel import MobileChannel
from .output.voice_channel import VoiceChannel
from .output.web_channel import WebChannel
from .registry import ChannelRegistry, channel_registry, register_default_channels

__all__ = [
    "Channel",
    "ChannelContext",
    "ChannelRegistry",
    "channel_registry",
    "register_default_channels",
    "IncomingMessage",
    "InputChannel",
    "VoiceChannel",
    "WebChannel",
    "MobileChannel",
    "McpMessageChannel",
    "voice_input",
    "mobile_input",
    "web_input",
]
