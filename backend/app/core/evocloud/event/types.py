"""
EvoCloud Device Event Types
===========================

Event type constants for device connection/disconnection.
"""

from enum import Enum


class DeviceEventType(str, Enum):
    """Device connection event types."""
    CONNECTED = "device.connected"
    DISCONNECTED = "device.disconnected"
