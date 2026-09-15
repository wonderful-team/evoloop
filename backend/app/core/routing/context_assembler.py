"""Assemble multi-turn context for the high-level intent classifier."""

from __future__ import annotations

from app.core.routing.constants import (
    DOMAIN_AMBIGUOUS,
    INTENT_DIRECT_ANSWER,
    INTENT_MACRO_TASK,
)
from app.core.routing.conversation_state import _ANAPHORA_RE

# Non-knowledge L0 labels.  When the immediately preceding turn is one of these,
# an anaphoric reference is likely pointing to an entity from a turn earlier than
# the last one, so we include the full rolling history.
_NON_KNOWLEDGE_PREVIOUS_INTENTS: set[str] = {
    INTENT_MACRO_TASK,
    INTENT_DIRECT_ANSWER,
    DOMAIN_AMBIGUOUS,
}


def _needs_context(text: str, previous_intent: str | None) -> bool:
    if not previous_intent:
        return False
    return bool(_ANAPHORA_RE.search(text))


def build_high_intent_input(
    text: str,
    session_history: list[str] | None = None,
    *,
    previous_intent: str | None = None,
    max_history: int = 1,
) -> str:
    """Return the text used by the high-level intent classifier.

    History is only included when the current turn clearly depends on the prior
    context (anaphora markers such as 它/这个/刚才, or very short utterances).
    When the immediately preceding turn is a local action / macro /
    ambiguous, an anaphora is likely referring to an earlier entity, so the full
    rolling history is used.  Otherwise only the most recent turn is used to
    avoid topic drift caused by concatenating unrelated previous turns.
    """
    history = session_history or []
    if not history:
        return text

    if not _needs_context(text, previous_intent):
        return text

    # For anaphoric turns preceded by a non-knowledge action, use the full
    # rolling history so a local action/macro in between does not hide the
    # referenced entity.
    if previous_intent in _NON_KNOWLEDGE_PREVIOUS_INTENTS:
        context = list(history) + [text]
    else:
        context = list(history[-max_history:]) + [text]
    return "；".join(context)


__all__ = ["build_high_intent_input"]
