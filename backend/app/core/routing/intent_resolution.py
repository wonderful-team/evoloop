"""Context-aware BERT intent-to-action resolution.

This module takes a BERT intent label, applies context-aware redirects, guards,
device keyword overrides, and macro resolution, returning an
L0 action tuple (``action, args``) that the ``DecisionBuilder`` can turn into a
``RouteDecision``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.routing.context_probe import resolve_context
from app.core.routing.macro_resolver import MacroResolver
from app.core.routing.routing_data import RoutingLanguageStore, get_store

logger = logging.getLogger(__name__)


class IntentResolver:
    """Resolve a BERT intent label into an L0 action tuple."""

    def __init__(
        self,
        routing_store: RoutingLanguageStore | None = None,
        macro_resolver: MacroResolver | None = None,
        context_probe: Callable[[], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self._routing_store = routing_store or get_store()
        self._macro_resolver = macro_resolver or MacroResolver()
        self._context_probe = context_probe or resolve_context

    async def resolve(
        self,
        intent_name: str,
        text: str,
        project_id: int,
    ) -> tuple[str, dict[str, Any]] | None:
        """Map a BERT intent label to an L0 action tuple (action, args).

        Returns ``None`` when the intent should be delegated to the agent
        (complex query) or rejected by a guard regex.
        """
        # 1. Context-aware redirect
        if intent_name in self._routing_store.context_map:
            intent_name = await self._redirect_by_context(intent_name)

        # 2. Explicit complex-query intent -> delegate to agent
        if intent_name == self._routing_store.complex_query_intent:
            logger.info(
                "[intent_resolver] BERT classified %r as %r, delegating to agent",
                text,
                intent_name,
            )
            return None

        # 3. Intent-specific guards
        guard = self._routing_store.intent_guards.get(intent_name)
        if guard and not re.search(guard, text):
            return None

        # 4. Device keyword redirect
        candidates = self._build_candidates(intent_name, text)

        # 5. Macro resolution
        macro_match = await self._macro_resolver.resolve(candidates, text, project_id)
        if macro_match is not None:
            return macro_match

        # 6. No L0 match -> delegate to the agent.
        return None

    async def _redirect_by_context(self, intent_name: str) -> str:
        """Apply the active-app/phone context map to ``intent_name``."""
        mapping = self._routing_store.context_map[intent_name]
        target = mapping.get("__default__", "")
        ctx = await self._context_probe()

        for app_key, target_intent in mapping.items():
            if app_key in ("__default__", "__phone__"):
                continue
            if app_key.lower() in ctx["app"].lower():
                target = target_intent
                break

        if ctx.get("phone_connected") and "__phone__" in mapping:
            target = mapping["__phone__"]

        return target or intent_name

    def _build_candidates(self, intent_name: str, text: str) -> list[str]:
        """Produce candidate intent names, applying device keyword overrides."""
        candidates = [intent_name, intent_name.replace("_", " ")]
        trigger_intents = self._routing_store.device_intent_trigger_intents
        for keyword, targets in self._routing_store.device_intents.items():
            if keyword in text and intent_name in trigger_intents:
                return targets
        return candidates


__all__ = ["IntentResolver"]
