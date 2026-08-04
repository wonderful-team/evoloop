"""Command router — source-agnostic intent classification and routing decision.

This module extracts the matching/decision logic previously embedded in
``app.core.routing.channels.voice`` so that voice, chat, and any future channel
can share the same catalog and classification rules.  It returns a
``RouteDecision`` instead of performing channel-specific side effects; channel
adapters in ``app.core.routing.channels`` are responsible for
presentation/execution.

The pipeline is:

1. Direct navigation routes (exact phrase match).
2. BERT intent classification + context/guard/macro resolution.
3. Deterministic local matcher fallback.
4. L1 domain classifier for agent delegation.  The agent engine maps the
   domain to a functional intent and module list.

Implementation details such as multi-turn state, anaphora detection, macro
resolution, domain-to-intent mapping, and decision assembly are delegated to
the modules under ``app.core.routing`` and ``app.core.engine`` so this file
stays focused on orchestration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.routing import domain_classifier
from app.core.routing.action_classifier import predict as classifier_predict
from app.core.routing.compound_detector import is_compound_intent
from app.core.routing.context_assembler import build_high_intent_input
from app.core.routing.conversation_state import (
    _get_thread_intent_state,
    _update_thread_intent_state,
)
from app.core.routing.decision_builder import build_decision
from app.core.routing.domain_classifier import CONFIDENCE_THRESHOLD as HIGH_INTENT_THRESHOLD
from app.core.routing.intent_resolution import IntentResolver
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.matcher_cache import matcher_cache
from app.core.routing.navigation_macro_cache import (
    NavigationMacroCache,
    get_navigation_macro_cache,
)
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import IntentHint, RouteDecision

logger = logging.getLogger(__name__)

_routing_store = get_store()


class CommandRouter:
    """Source-agnostic command router: catalog + classifiers -> RouteDecision."""

    def __init__(
        self,
        local_matcher: LocalMatcher | None = None,
        intent_resolver: IntentResolver | None = None,
        nav_macro_cache: NavigationMacroCache | None = None,
    ) -> None:
        self._local_matcher = local_matcher
        self._intent_resolver = intent_resolver or IntentResolver()
        self._nav_macro_cache = nav_macro_cache or get_navigation_macro_cache()

    async def _get_local_matcher(self) -> LocalMatcher:
        if self._local_matcher is not None:
            return self._local_matcher
        return await matcher_cache.get()

    async def resolve(
        self,
        text: str,
        *,
        thread_id: str = "",
        project_id: int = 0,
        source: str = "voice",
        context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        """Classify ``text`` and return a channel-independent routing decision.

        Every return path records the resolved intent label into the per-thread
        L0 state (``previous_intent`` + rolling ``session_history``) so that a
        subsequent turn carrying an anaphora (它/这个/刚才) can fall back to
        semantic recall even when it routes to a non-agent path.

        ``context`` is accepted for interface compatibility but is currently
        unused; context probing is performed internally by ``IntentResolver``.
        """
        del context  # reserved for future source/channel context
        previous_intent, session_history = _get_thread_intent_state(thread_id)

        # 1. Direct navigation macros (exact phrase match against DB presets).
        nav_macro = await self._nav_macro_cache.get(text)
        if nav_macro is not None:
            decision = RouteDecision(
                status="routed",
                target_type="macro",
                target={"type": "macro", "id": nav_macro.id},
                params={"route": nav_macro.route, "feedback": nav_macro.feedback},
                confidence=1.0,
                intent_hint=IntentHint(
                    intent="macro_task",
                    confidence=1.0,
                    suggested_modules=["Base", "Macro"],
                    reason="navigation macro match",
                    previous_intent=previous_intent,
                    session_history=session_history,
                ),
                source=source,
            )
            self._record_thread_intent(thread_id, decision, text)
            return decision

        # 2. Compound / multi-intent guard: bypass L0 and delegate to agent.
        if is_compound_intent(text):
            intent_hint_obj = IntentHint(
                intent="domain_classified",
                domain="multi_intent",
                confidence=1.0,
                suggested_modules=[],
                reason="compound_intent",
                previous_intent=previous_intent,
                session_history=session_history,
            )
            decision = RouteDecision(
                status="delegate",
                target_type="agent",
                target={"type": "agent"},
                params={},
                confidence=1.0,
                intent_hint=intent_hint_obj,
                source=source,
                raw="multi_intent",
            )
            self._record_thread_intent(thread_id, decision, text)
            return decision

        # 3. BERT intent classification + intent-specific resolution
        intent_name, margin = await asyncio.to_thread(classifier_predict, text)
        l0_match = None
        if intent_name:
            l0_match = await self._intent_resolver.resolve(
                intent_name, text, project_id
            )
        if l0_match is not None:
            action, args = l0_match
            decision = build_decision(
                action,
                args,
                margin,
                source,
                previous_intent=previous_intent,
                session_history=session_history,
            )
            self._record_thread_intent(thread_id, decision, text)
            return decision

        # 4. Deterministic local matcher fallback
        matcher = await self._get_local_matcher()
        l0_match = matcher.match(text)
        if l0_match is not None:
            action, args = l0_match
            decision = build_decision(
                action,
                args,
                1.0,
                source,
                previous_intent=previous_intent,
                session_history=session_history,
            )
            self._record_thread_intent(thread_id, decision, text)
            return decision

        # 5. High-level intent classifier (L1) with multi-turn context
        l1_input = build_high_intent_input(text, session_history, previous_intent=previous_intent)
        l1_label, l1_conf = await asyncio.to_thread(domain_classifier.predict, l1_input)
        if l1_label and l1_conf >= HIGH_INTENT_THRESHOLD:
            intent_hint_obj = domain_classifier.to_intent_hint(
                l1_label,
                l1_conf,
                previous_intent=previous_intent,
                session_history=session_history,
            )
            raw_label = l1_label
        else:
            # L1 unavailable or low confidence: delegate to agent as ambiguous.
            intent_hint_obj = IntentHint(
                intent="domain_classified",
                domain="ambiguous",
                confidence=0.0,
                suggested_modules=[],
                reason="L1 classifier unavailable or low confidence",
                previous_intent=previous_intent,
                session_history=session_history,
            )
            raw_label = "ambiguous"

        decision = RouteDecision(
            status="delegate",
            target_type="agent",
            target={"type": "agent"},
            params={},
            confidence=l1_conf if raw_label != "ambiguous" else 0.0,
            intent_hint=intent_hint_obj,
            source=source,
            raw=raw_label,
        )
        self._record_thread_intent(thread_id, decision, text)
        return decision

    @staticmethod
    def _record_thread_intent(thread_id: str, decision: RouteDecision, text: str) -> None:
        """Persist the resolved intent label on the per-thread L0 state.

        All five resolve paths funnel through here so a subsequent anaphora turn
        can pick up the previous intent/domain regardless of whether the prior turn
        was a local action, macro, builtin, or agent delegation.

        The recorded label is the *most descriptive* key available on the
        decision: when ``intent_hint.domain`` is set (L1 path) we prefer it over
        the ``domain_classified`` sentinel stored in ``intent``, because
        ``domain`` carries the actual functional domain (e.g. ``environment``)
        while ``intent`` is just a placeholder the engine later resolves. For
        non-L1 paths (L0/macro/builtin/local) ``domain`` is absent and we fall
        back to the concrete ``intent`` label (e.g. ``macro_task``). ``raw`` is
        kept on the decision for debugging only and intentionally not used here
        so the recorded key stays consistent whether L1 succeeded or fell back
        to the ambiguous sentinel.
        """
        intent: str | None = None
        if decision.intent_hint:
            intent = decision.intent_hint.domain or decision.intent_hint.intent
        _update_thread_intent_state(thread_id, intent, text)


__all__ = ["CommandRouter"]
