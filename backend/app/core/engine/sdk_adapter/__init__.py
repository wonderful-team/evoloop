"""OpenHands SDK integration boundary.

The module is intentionally imported lazily by the legacy kernel switch.  This
keeps the legacy path importable during a staged rollout and makes the adapter
the only place that knows about OpenHands SDK objects.
"""

from __future__ import annotations


class SDKAdapterError(RuntimeError):
    """Base error for SDK adapter failures."""


__all__ = ["SDKAdapterError"]
