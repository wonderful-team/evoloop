"""Device-kind constants shared across the L0 routing layer.

The L0 device-context disambiguation stores a per-thread device label
(``conversation_state``) and classifies macros into a device kind
(``MacroDeviceMap``).  These two realities use the same vocabulary; a single
definition here keeps the strings consistent and makes ``ruff`` or a typecheck
catch a typo like ``"phoen"`` at dev time.
"""

from __future__ import annotations

from enum import Enum


class DeviceKind(str, Enum):
    """Device category bound to a macro or a thread context."""

    PHONE = "phone"
    DESKTOP = "desktop"


__all__ = ["DeviceKind"]
