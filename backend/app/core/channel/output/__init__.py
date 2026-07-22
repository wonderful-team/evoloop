"""
Output channels — deliver agent results to external transports.

Each channel implements ``send()`` for publishing ``MessageBlock``,
``BaseStreamEvent``, or ``EventBase`` payloads.
"""

from ..base import Channel, ChannelContext

__all__ = [
    "Channel",
    "ChannelContext",
]
