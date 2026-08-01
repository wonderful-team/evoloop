"""Test fixtures for L0 routing tests.

These are the historical init_spec constants that were moved out of production
so that tests can still exercise the full LocalMatcher algorithm (slot
dictionaries, multiple action families, etc.) without depending on the live
macros table. Production code now loads only builtin templates from
``app/core/routing/data/{lang}/templates.yaml`` (typically zh) and relies on DB
preset macros for everything else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.utils.yaml import safe_yaml_loads

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "l0_test_templates.yaml"

_data = safe_yaml_loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

_VOICE_LOCAL_ACTIONS: list[dict[str, Any]] = list(_data.get("voice_local_actions", []))
_TEMPLATES: list[dict[str, Any]] = list(_data.get("templates", []))
_ALIASES: dict[str, str] = dict(_data.get("aliases", {}))
_DELTA_DICT: dict[str, str] = dict(
    _data.get("slot_dictionaries", {}).get("delta", {})
)
_KEY_DICT: dict[str, str] = dict(
    _data.get("slot_dictionaries", {}).get("key", {})
)

__all__ = [
    "_VOICE_LOCAL_ACTIONS",
    "_TEMPLATES",
    "_ALIASES",
    "_DELTA_DICT",
    "_KEY_DICT",
]
