"""Command router — source-agnostic intent classification and routing decision.

This module extracts the matching/decision logic previously embedded in
``app.core.routing.channels.voice`` so that voice, chat, and any future channel
can share the same catalog and classification rules.  It returns a
``RouteDecision`` instead of performing channel-specific side effects; channel
adapters in ``app.core.routing.channels`` are responsible for
presentation/execution.

The pipeline is:

1. Direct navigation routes (exact phrase match).
2. Deterministic template match over RouteCatalog macro trigger patterns.
3. BERT intent classification + context/guard/macro resolution.
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
    _get_thread_device_context,
    _get_thread_intent_state,
    _update_thread_device_context,
    _update_thread_intent_state,
)
from app.core.routing.decision_builder import build_decision
from app.core.routing.device_kind import DeviceKind
from app.core.routing.domain_classifier import (
    CONFIDENCE_THRESHOLD as HIGH_INTENT_THRESHOLD,
)
from app.core.routing.intent_resolution import IntentResolver
from app.core.routing.macro_device_map import get_macro_device_map
from app.core.routing.matcher_cache import matcher_cache
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import (
    DOMAIN_AMBIGUOUS,
    DOMAIN_MULTI_INTENT,
    INTENT_DOMAIN_CLASSIFIED,
    INTENT_MACRO_TASK,
    IntentHint,
    RouteDecision,
)

logger = logging.getLogger(__name__)

_routing_store = get_store()


class CommandRouter:
    """Source-agnostic command router: catalog + classifiers -> RouteDecision."""

    def __init__(
        self,
        intent_resolver: IntentResolver | None = None,
    ) -> None:
        self._intent_resolver = intent_resolver or IntentResolver()

    async def resolve(
        self,
        text: str,
        *,
        thread_id: str = "",
        project_id: int = 0,
        source: str = "voice",
        context: dict[str, Any] | None = None,
        skip_l0: bool = False,
    ) -> RouteDecision:
        """Classify ``text`` and return a channel-independent routing decision.

        Every return path records the resolved intent label into the per-thread
        L0 state (``previous_intent`` + rolling ``session_history``) so that a
        subsequent turn carrying an anaphora (它/这个/刚才) can fall back to
        semantic recall even when it routes to a non-agent path.

        When ``skip_l0`` is True (text ``web`` channel), the L0 layer is
        bypassed entirely: L0 only serves voice shortcut commands (navigation /
        macros / local actions) that must resolve locally in milliseconds. A
        text chat turn is always an agent conversation, so the decision jumps
        straight to the L1 domain classifier and delegates to the agent.

        ``context`` is accepted for interface compatibility but is currently
        unused; context probing is performed internally by ``IntentResolver``.
        """
        del context  # reserved for future source/channel context
        previous_intent, session_history = _get_thread_intent_state(thread_id)

        if skip_l0:
            decision = await self._l1_delegate(
                text,
                session_history,
                previous_intent=previous_intent,
                source=source,
            )
            await self._record_thread_intent(thread_id, decision, text)
            return decision

        # 1. Direct navigation macros (exact phrase match against DB presets).
        from app.core.learning.macro.service import MacroService

        nav_macro = await MacroService.resolve_navigation_macro(text)
        if nav_macro is not None:
            nav_id, nav_route, nav_feedback = nav_macro
            decision = RouteDecision(
                status="routed",
                target_type="macro",
                target={"type": "macro", "id": nav_id},
                params={"route": nav_route, "feedback": nav_feedback},
                confidence=1.0,
                intent_hint=IntentHint(
                    intent=INTENT_MACRO_TASK,
                    confidence=1.0,
                    suggested_modules=["Base", "Macro"],
                    reason="navigation macro match",
                    previous_intent=previous_intent,
                    session_history=session_history,
                ),
                source=source,
            )
            await self._record_thread_intent(thread_id, decision, text)
            return decision

        # 2. Template layer: deterministic RouteCatalog macro trigger patterns.
        #    The anchored LocalMatcher runs before the BERT classifier so literal
        #    commands ("打开微信", "打开腾讯会议") bind to the matching macro
        #    regardless of embedding margin.  Anchoring guarantees the whole
        #    utterance must be the command; anything else falls through to BERT.
        template_matcher = await matcher_cache.get_local_matcher()
        if template_matcher is not None:
            template_hit = template_matcher.match(text, project_id=project_id)
            if template_hit is not None:
                action, args = template_hit
                action = await self._disambiguate_device_macro(action, thread_id)
                decision = build_decision(
                    action,
                    args,
                    1.0,
                    source,
                    previous_intent=previous_intent,
                    session_history=session_history,
                )
                await self._record_thread_intent(thread_id, decision, text)
                return decision

        # 3. Compound / multi-intent guard: bypass L0 and delegate to agent.
        if is_compound_intent(text):
            intent_hint_obj = IntentHint(
                intent=INTENT_DOMAIN_CLASSIFIED,
                domain=DOMAIN_MULTI_INTENT,
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
                raw=DOMAIN_MULTI_INTENT,
            )
            await self._record_thread_intent(thread_id, decision, text)
            return decision

        # 4. BERT intent classification + intent-specific resolution
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
            await self._record_thread_intent(thread_id, decision, text)
            return decision

        # 5. High-level intent classifier (L1) with multi-turn context
        decision = await self._l1_delegate(
            text,
            session_history,
            previous_intent=previous_intent,
            source=source,
        )
        await self._record_thread_intent(thread_id, decision, text)
        return decision

    async def _l1_delegate(
        self,
        text: str,
        session_history: list[str],
        *,
        previous_intent: str | None,
        source: str,
    ) -> RouteDecision:
        """Run the L1 domain classifier and build an agent-delegation decision.

        Shared by the L0-miss path and the ``skip_l0`` (text) path so both
        produce the same ``IntentHint`` + ``RouteDecision`` shape.
        """
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
                intent=INTENT_DOMAIN_CLASSIFIED,
                domain=DOMAIN_AMBIGUOUS,
                confidence=0.0,
                suggested_modules=[],
                reason="L1 classifier unavailable or low confidence",
                previous_intent=previous_intent,
                session_history=session_history,
            )
            raw_label = DOMAIN_AMBIGUOUS

        return RouteDecision(
            status="delegate",
            target_type="agent",
            target={"type": "agent"},
            params={},
            confidence=l1_conf if raw_label != DOMAIN_AMBIGUOUS else 0.0,
            intent_hint=intent_hint_obj,
            source=source,
            raw=raw_label,
        )

    @staticmethod
    async def _disambiguate_device_macro(action: str, thread_id: str) -> str:
        """Re-target a device-agnostic macro hit to its phone twin.

        When the thread's device context is ``phone`` (the previous turn ran a
        phone macro, e.g. 手机播放音乐) and the freshly matched template macro
        is a device-agnostic media macro with a phone counterpart (e.g. 下一曲),
        the decision is re-targeted to the phone twin (手机切歌).  A no-op for
        everything else: phone macros, macros without a twin, and threads with
        no phone context.
        """
        if not action.startswith("macro:"):
            return action
        macro_id = int(action.split(":", 1)[1])
        if _get_thread_device_context(thread_id) != DeviceKind.PHONE:
            return action
        twin = await get_macro_device_map().phone_twin(macro_id)
        if twin is None or twin == macro_id:
            return action
        logger.info(
            "[router] device context disambiguation: macro %d -> %d (thread=%s)",
            macro_id,
            twin,
            thread_id,
        )
        return f"macro:{twin}"

    @staticmethod
    async def _record_thread_intent(thread_id: str, decision: RouteDecision, text: str) -> None:
        """Persist the resolved intent label on the per-thread L0 state.

        All resolve paths funnel through here so a subsequent anaphora turn
        can pick up the previous intent/domain regardless of whether the prior turn
        was a local action, macro, or agent delegation.

        The recorded label is the *most descriptive* key available on the
        decision: when ``intent_hint.domain`` is set (L1 path) we prefer it over
        the ``domain_classified`` sentinel stored in ``intent``, because
        ``domain`` carries the actual functional domain (e.g. ``environment``)
        while ``intent`` is just a placeholder the engine later resolves. For
        non-L1 paths (L0/macro/local) ``domain`` is absent and we fall
        back to the concrete ``intent`` label (e.g. ``macro_task``). ``raw`` is
        kept on the decision for debugging only and intentionally not used here
        so the recorded key stays consistent whether L1 succeeded or fell back
        to the ambiguous sentinel.
        """
        intent: str | None = None
        if decision.intent_hint:
            intent = decision.intent_hint.domain or decision.intent_hint.intent
        _update_thread_intent_state(thread_id, intent, text)

        # Device context for the next turn's L0 disambiguation: a macro that
        # carries the phone marker sets the thread to PHONE, a plain macro
        # clears it back to DESKTOP so explicit desktop actions win.
        if decision.target_type == "macro":
            macro_id = decision.target.get("id")
            if isinstance(macro_id, int):
                device = await get_macro_device_map().device_of(macro_id)
                if device is not None:
                    _update_thread_device_context(thread_id, device)


__all__ = ["CommandRouter"]
