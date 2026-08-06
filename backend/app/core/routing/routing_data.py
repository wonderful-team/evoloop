"""Routing data loaders for the L0 routing layer.

Loads language-specific YAML files from ``app/core/routing/data/{lang}/``.
The active language is read from ``SystemConfigService.get_value(\"LANGUAGE\", \"zh\")``
at import time; a reload API is provided for runtime language changes.

This module exposes a single ``RoutingLanguageStore`` singleton rather than
mutable module-level constants. Reading code always sees a consistent snapshot;
reload atomically replaces the whole underlying mapping.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.infrastructure.config.service import SystemConfigService
from app.utils.yaml import YAMLError, safe_yaml_loads

logger = logging.getLogger(__name__)

_ROUTING_DATA_BASE = Path(__file__).resolve().parent / "data"
_DEFAULT_LANG = "zh"


def _get_active_language() -> str:
    """Read the configured LANGUAGE code, falling back to zh."""
    try:
        lang = SystemConfigService.get_value("LANGUAGE", _DEFAULT_LANG)
    except Exception:
        logger.debug(
            "[routing_data] failed to read LANGUAGE, falling back to %s",
            _DEFAULT_LANG,
            exc_info=True,
        )
        return _DEFAULT_LANG
    return (lang or _DEFAULT_LANG).strip() or _DEFAULT_LANG


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a routing YAML file, returning an empty mapping on failure."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("[routing_data] missing %s: %s", path, exc)
        return {}
    try:
        data = safe_yaml_loads(content)
    except YAMLError as exc:
        logger.warning("[routing_data] invalid YAML in %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("[routing_data] %s root must be a mapping", path)
        return {}
    return data


def _build_routing_data(lang: str) -> dict[str, Any]:
    """Load all routing data for the given language code."""
    lang_dir = _ROUTING_DATA_BASE / lang

    templates_data = _load_yaml(lang_dir / "templates.yaml")
    intent_overrides = _load_yaml(lang_dir / "intent_overrides.yaml")
    builtin_responses = _load_yaml(lang_dir / "builtin_responses.yaml")

    # Builtin templates / aliases / voice local actions / static app slots
    voice_local_actions: list[dict[str, Any]] = list(templates_data.get("voice_local_actions", []))
    templates: list[dict[str, Any]] = list(templates_data.get("templates", []))
    aliases: dict[str, str] = dict(templates_data.get("aliases", {}))
    apps: list[dict[str, Any]] = list(templates_data.get("apps", []))

    # Context-aware intent redirect
    context_map: dict[str, dict[str, str]] = {
        k: dict(v) if isinstance(v, dict) else {}
        for k, v in intent_overrides.get("context_map", {}).items()
    }

    # BERT intent label -> builtin L0 action
    builtin_aliases: dict[str, str] = dict(intent_overrides.get("builtin_aliases", {}))

    # BERT intent label that always delegates to the agent (complex query).
    complex_query_intent: str = str(intent_overrides.get("complex_query_intent", ""))

    # Intent-specific guard regexes: intent -> required regex.
    intent_guards_raw = intent_overrides.get("intent_guards", {})
    intent_guards: dict[str, str] = {
        str(k): str(v)
        for k, v in intent_guards_raw.items()
        if isinstance(k, str) and isinstance(v, str)
    }

    # Intents that allow device keyword redirects to override candidates.
    device_intent_trigger_intents: frozenset[str] = frozenset(
        v
        for v in intent_overrides.get("device_intent_trigger_intents", [])
        if isinstance(v, str)
    )

    # Canonical built-in L0 actions.
    builtin_actions: frozenset[str] = frozenset(
        v for v in intent_overrides.get("builtin_actions", [])
        if isinstance(v, str)
    )

    # Device keyword -> candidate intent names for macro resolution
    device_intents: dict[str, list[str]] = {
        k: list(v) if isinstance(v, list) else []
        for k, v in intent_overrides.get("device_intents", {}).items()
    }

    # Slot-value prefixes stripped from raw text
    slot_prefixes: list[str] = list(intent_overrides.get("slot_prefixes", []))

    # Response strings for builtins / macros / local actions
    builtin_responses_clean: dict[str, dict[str, str]] = {}
    for section, values in builtin_responses.items():
        if isinstance(values, dict):
            builtin_responses_clean[section] = {
                k: str(v) for k, v in values.items()
                if isinstance(v, str | int)
            }

    return {
        "language": lang,
        "VOICE_LOCAL_ACTIONS": voice_local_actions,
        "TEMPLATES": templates,
        "ALIASES": aliases,
        "APPS": apps,
        "CONTEXT_MAP": context_map,
        "BUILTIN_ALIASES": builtin_aliases,
        "COMPLEX_QUERY_INTENT": complex_query_intent,
        "INTENT_GUARDS": intent_guards,
        "DEVICE_INTENTS": device_intents,
        "DEVICE_INTENT_TRIGGER_INTENTS": device_intent_trigger_intents,
        "BUILTIN_ACTIONS": builtin_actions,
        "SLOT_PREFIXES": slot_prefixes,
        "BUILTIN_RESPONSES": builtin_responses_clean,
    }


class RoutingLanguageStore:
    """Language-specific routing data snapshot.

    The store is initialized at import time with the active language. It can be
    reloaded asynchronously at runtime; reload replaces the entire underlying
    mapping so readers always see a consistent snapshot.
    """

    def __init__(self, lang: str) -> None:
        self._lock = asyncio.Lock()
        self._data = _build_routing_data(lang)

    @property
    def lang(self) -> str:
        return self._data["language"]

    @property
    def voice_local_actions(self) -> list[dict[str, Any]]:
        return self._data["VOICE_LOCAL_ACTIONS"]

    @property
    def templates(self) -> list[dict[str, Any]]:
        return self._data["TEMPLATES"]

    @property
    def aliases(self) -> dict[str, str]:
        return self._data["ALIASES"]

    @property
    def apps(self) -> list[dict[str, Any]]:
        return self._data["APPS"]

    @property
    def context_map(self) -> dict[str, dict[str, str]]:
        return self._data["CONTEXT_MAP"]

    @property
    def builtin_aliases(self) -> dict[str, str]:
        return self._data["BUILTIN_ALIASES"]

    @property
    def complex_query_intent(self) -> str:
        return self._data["COMPLEX_QUERY_INTENT"]

    @property
    def intent_guards(self) -> dict[str, str]:
        return self._data["INTENT_GUARDS"]

    @property
    def device_intents(self) -> dict[str, list[str]]:
        return self._data["DEVICE_INTENTS"]

    @property
    def device_intent_trigger_intents(self) -> frozenset[str]:
        return self._data["DEVICE_INTENT_TRIGGER_INTENTS"]

    @property
    def builtin_actions(self) -> frozenset[str]:
        return self._data["BUILTIN_ACTIONS"]

    @property
    def slot_prefixes(self) -> list[str]:
        return self._data["SLOT_PREFIXES"]

    @property
    def builtin_responses(self) -> dict[str, dict[str, str]]:
        return self._data["BUILTIN_RESPONSES"]

    async def reload(self, lang: str) -> None:
        """Atomically replace the entire data snapshot for ``lang``."""
        new_data = await asyncio.to_thread(_build_routing_data, lang)
        async with self._lock:
            self._data = new_data
        logger.info("[routing_data] loaded routing data for language %s", lang)


def get_store() -> RoutingLanguageStore:
    """Return the module singleton ``RoutingLanguageStore``."""
    return _store


# Module singleton initialized at import time with the active language.
_store = RoutingLanguageStore(_get_active_language())


__all__ = [
    "RoutingLanguageStore",
    "get_store",
]
