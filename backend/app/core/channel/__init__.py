"""
Channel abstraction — unified interface for message delivery across transports.

A Channel wraps the transport-specific serialization and dispatch logic
(SSE/EventBus, WebSocket, IM webhook, etc.) behind a single `send()` interface.

The MessagePublisher delegates to a ChannelRegistry instead of hardcoding
_send_to_sse / _publish_mobile. New transports (WeChat, Feishu, DingTalk,
Telegram, Slack, ...) are added by implementing Channel and registering
with the registry — no changes to MessagePublisher needed.
"""

from .base import Channel, ChannelContext
from .mobile_channel import MobileChannel
from .registry import ChannelRegistry, channel_registry, register_default_channels
from .voice_channel import VoiceChannel
from .web_channel import WebChannel

__all__ = [
    "Channel",
    "ChannelContext",
    "ChannelRegistry",
    "channel_registry",
    "register_default_channels",
    "VoiceChannel",
    "WebChannel",
    "MobileChannel",
]
