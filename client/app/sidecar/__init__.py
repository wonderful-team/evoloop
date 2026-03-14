"""
Sidecar Module - JSON Lines communication with Tauri.

This module provides the protocol and handlers for Sidecar mode communication
between Tauri (center) and Client (execution layer).
"""

from app.sidecar.protocol import SidecarProtocol, get_protocol, send_event_sync

__all__ = [
    "SidecarProtocol",
    "get_protocol",
    "send_event_sync",
]
