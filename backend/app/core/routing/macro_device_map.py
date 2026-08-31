"""Device-context macro mapping for the L0 routing layer.

The L0 template layer binds a phrase to a single macro with no notion of
device context: "切歌" resolves to the macOS 下一曲 macro even when the user
just told the assistant to play music on the phone.  This module pairs a
device-agnostic macro with the phone macro that targets the same bare subject
phrase, so the router can re-target "切歌" to the 手机切歌 macro when the
thread's device context is ``phone``.

Device vocabulary is **data-driven**: the set of device markers (``手机``,
``phone``, ...) lives in ``intent_overrides.yaml`` as ``device_markers``.  A
macro is phone-targeting when any of its trigger patterns carries a marker; its
phone core is the pattern with the marker prefix stripped.  A device-agnostic
macro and a phone macro are paired when a bare trigger phrase collides.  No
macro ids are hard-coded.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.routing.device_kind import DeviceKind
from app.core.routing.routing_data import get_store

logger = logging.getLogger(__name__)


class MacroDeviceMap:
    """Catalog-derived device/twin cache.

    - ``device_of(macro_id) -> DeviceKind | None``
    - ``phone_twin(macro_id) -> phone macro id | None``

    Device markers are read from the routing store (``device_markers``).
    Lazy, TTL-based so runtime macro and config changes propagate without a
    restart.
    """

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._device: dict[int, DeviceKind] = {}
        self._twin: dict[int, int] = {}
        self._last_refresh: float = 0.0
        self._refreshing = False

    async def device_of(self, macro_id: int) -> DeviceKind | None:
        await self._maybe_refresh()
        return self._device.get(macro_id)

    async def phone_twin(self, macro_id: int) -> int | None:
        await self._maybe_refresh()
        return self._twin.get(macro_id)

    async def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_refresh < self._ttl and self._device:
            return
        async with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        try:
            device, twin = await self._load()
            self._device, self._twin = device, twin
            self._last_refresh = time.monotonic()
            logger.debug(
                "[macro_device_map] refreshed %d devices, %d phone twins",
                len(device),
                len(twin),
            )
        except Exception:
            logger.exception("[macro_device_map] failed to refresh")
        finally:
            async with self._lock:
                self._refreshing = False

    async def _load(self) -> tuple[dict[int, DeviceKind], dict[int, int]]:
        from app.core.learning.macro.service import MacroService

        markers = tuple(get_store().device_markers or [])
        marker_tokens = _marker_tokens(markers)

        macros = await MacroService.list_routable_macros()

        device: dict[int, DeviceKind] = {}
        # phone macro id -> bare subject cores (marker stripped).
        phone_cores: dict[int, set[str]] = {}
        # desktop macro id -> set of trigger phrases.
        desktop_phrases: dict[int, set[str]] = {}

        for macro in macros:
            triggers = [
                p for p in (macro.trigger_patterns or []) if isinstance(p, str) and p
            ]
            if not triggers:
                continue
            is_phone = _has_marker(triggers, markers)
            device[macro.id] = DeviceKind.PHONE if is_phone else DeviceKind.DESKTOP
            if is_phone:
                phone_cores[macro.id] = {
                    _strip_marker(t, marker_tokens) for t in triggers
                }
            else:
                desktop_phrases[macro.id] = set(triggers)

        twin: dict[int, int] = {}
        for desktop_id, phrases in desktop_phrases.items():
            for phone_id, cores in phone_cores.items():
                if phrases & cores:
                    twin[desktop_id] = phone_id
                    break
        return device, twin


def _marker_tokens(markers: tuple[str, ...]) -> tuple[str, ...]:
    """Expand markers into strippable tokens, longest first.

    A phone trigger usually reads ``<marker><上|在手机上>?<subject>``; we strip
    the marker itself and allow the glue word ``上``.  E.g. for ``手机``:
    ``手机``, ``手机上``, ``在手机上``.
    """
    tokens: set[str] = set()
    for marker in markers:
        tokens.add(marker)
        tokens.add(f"{marker}上")
        tokens.add(f"在{marker}上")
    return tuple(sorted(tokens, key=len, reverse=True))


def _has_marker(triggers: list[str], markers: tuple[str, ...]) -> bool:
    return any(m in t for t in triggers for m in markers)


def _strip_marker(phrase: str, marker_tokens: tuple[str, ...]) -> str:
    """Strip a leading device token, leaving the bare subject phrase."""
    text = phrase.strip()
    for token in marker_tokens:
        if text.startswith(token) and len(text) > len(token):
            return text[len(token) :].strip()
    return text


# Module singleton shared by the command router and tests.
macro_device_map = MacroDeviceMap()


def get_macro_device_map() -> MacroDeviceMap:
    return macro_device_map


__all__ = [
    "MacroDeviceMap",
    "macro_device_map",
    "get_macro_device_map",
]
