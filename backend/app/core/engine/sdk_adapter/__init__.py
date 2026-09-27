"""OpenHands SDK integration boundary.

The module is intentionally imported lazily by the legacy kernel switch.  This
keeps the legacy path importable during a staged rollout and makes the adapter
the only place that knows about OpenHands SDK objects.
"""

from __future__ import annotations


class SDKAdapterError(RuntimeError):
    """Base error for SDK adapter failures."""


class SDKToolExecutionError(SDKAdapterError):
    """Raised when an SDK tool wrapper cannot execute a native tool."""


__all__ = ["SDKAdapterError", "SDKToolExecutionError"]
