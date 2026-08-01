"""Best-effort pinyin utilities for routing modules.

The dependency is optional on the client and during first-run / non-Chinese
hosts; failures are captured and returned as ``None`` so callers can degrade.
"""

from __future__ import annotations

try:
    from pypinyin import lazy_pinyin  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    lazy_pinyin = None  # type: ignore[assignment]


def to_pinyin(text: str) -> str | None:
    """Return joined pinyin for ``text`` or ``None`` if pypinyin is missing.

    Keeps the routing layer defensive: callers can fall back to literal matching
    when pinyin is unavailable.
    """
    if lazy_pinyin is None:
        return None
    try:
        return "".join(lazy_pinyin(text))
    except (ValueError, RuntimeError, TypeError):
        return None
