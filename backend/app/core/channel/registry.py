"""
ChannelRegistry — manages all registered transport channels.

The MessagePublisher uses this registry to dispatch payloads to matching
channels by name. New transports are registered at startup.
"""

import logging
from typing import Iterator

from .base import Channel

logger = logging.getLogger(__name__)


class ChannelRegistry:
    """Registry of active transport channels keyed by name."""

    def __init__(self):
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register a channel. Replaces any existing channel with the same name."""
        if channel.name in self._channels:
            logger.info("[ChannelRegistry] Replacing channel '%s'", channel.name)
        self._channels[channel.name] = channel
        logger.info("[ChannelRegistry] Registered channel '%s'", channel.name)

    def unregister(self, name: str) -> Channel | None:
        """Remove and return a channel by name."""
        return self._channels.pop(name, None)

    def get(self, name: str) -> Channel | None:
        """Get a channel by name."""
        return self._channels.get(name)

    def has(self, name: str) -> bool:
        """Check if a channel is registered."""
        return name in self._channels

    def all(self) -> dict[str, Channel]:
        """Return all registered channels."""
        return dict(self._channels)

    def names(self) -> list[str]:
        """Return all registered channel names."""
        return list(self._channels.keys())

    def select(
        self,
        names: set[str] | None,
        payload_is_block: bool,
    ) -> list[Channel]:
        """
        Select channels matching the requested names, filtered by payload type.

        Args:
            names: Requested channel names. None = auto-select all compatible.
            payload_is_block: True if payload is a MessageBlock (vs stream event).

        Returns:
            List of channels to dispatch to, in registration order.
        """
        result: list[Channel] = []
        for ch in self._channels.values():
            if names is not None and ch.name not in names:
                continue
            if payload_is_block and not ch.accepts_blocks:
                continue
            if not payload_is_block and not ch.accepts_stream_events:
                continue
            result.append(ch)
        return result

    def __iter__(self) -> Iterator[Channel]:
        return iter(self._channels.values())

    def __len__(self) -> int:
        return len(self._channels)


#: Global singleton registry
channel_registry = ChannelRegistry()


def register_default_channels() -> None:
    """Register the built-in channels (SSE + Mobile + Voice). Called at app startup."""
    from .mobile_channel import MobileChannel
    from .voice_channel import VoiceChannel
    from .web_channel import WebChannel

    if not channel_registry.has("sse"):
        channel_registry.register(WebChannel())
    if not channel_registry.has("mobile"):
        channel_registry.register(MobileChannel())
    if not channel_registry.has("voice"):
        channel_registry.register(VoiceChannel())
