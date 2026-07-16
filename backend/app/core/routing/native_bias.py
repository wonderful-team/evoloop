"""
Native-macro app disambiguation bias (backlog: bare-command ambiguity).

Menu macros from every surveyed app share identical standard leaves
('放大', '存储为…', '撤销'). Retrieval + the route LLM cannot tell them
apart for bare commands ('把窗口放大'), and the corpus showed it (~64%
bare vs 95% qualified). Two deterministic signals resolve it without
touching the LLM:

1. Explicit app mention — '飞书左侧' must never land on Chrome even if
   the LLM picked wrong. Candidate names carry aliases ('Lark 飞书>…'),
   so a text-substring check suffices.
2. Frontmost app — for a truly bare command, the app the user is looking
   at is the overwhelmingly likely referent.

Applied AFTER the route-decision cache lookup: the bias is a function of
the live desktop, caching it would freeze stale context.

Only fires when a same-leaf rival from another surveyed app is present in
the candidate list; otherwise the decision passes through untouched.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.routing.schemas import RouteCandidate, RouteDecision

logger = logging.getLogger(__name__)


def _leaf(name: str) -> str | None:
    return name.rsplit(">", 1)[-1].strip() if ">" in name else None


def _app_aliases(name: str, all_names: list[str]) -> set[str]:
    """Tokens distinctive to this macro's name within the candidate set.

    Rivals share the leaf ('放大') and root ('窗口') tokens by construction,
    so those cancel out; what remains is the app identity
    ({'chrome'} / {'lark', '飞书'}). Splitting on whitespace AND '>' so path
    segments contribute tokens too.
    """
    def tokens(n: str) -> set[str]:
        return {t.lower() for seg in n.split(">") for t in seg.split() if t}

    own = tokens(name)
    others: set[str] = set()
    for other in all_names:
        if other != name:
            others |= tokens(other)
    return own - others


def apply_native_app_bias(
    decision: RouteDecision,
    candidates: list[RouteCandidate],
    text: str,
    active_app: str | None,
) -> RouteDecision:
    if decision.status != "routed" or decision.target_type != "macro":
        return decision
    macro_id = (decision.target or {}).get("id")
    picked = next((c for c in candidates if c.id == f"macro:{macro_id}"), None)
    if picked is None:
        return decision
    leaf = _leaf(picked.name)
    if not leaf:
        return decision

    rivals = [
        c
        for c in candidates
        if c.id != picked.id and c.id.startswith("macro:") and _leaf(c.name) == leaf
    ]
    if not rivals:
        return decision

    lowered = text.lower()
    names = [c.name for c in candidates]
    picked_aliases = _app_aliases(picked.name, names)
    if any(alias in lowered for alias in picked_aliases):
        return decision  # user explicitly named the picked app

    chosen: RouteCandidate | None = None
    for rival in rivals:
        if any(alias in lowered for alias in _app_aliases(rival.name, names)):
            chosen = rival
            break
    if chosen is None and active_app:
        active = active_app.lower()
        for rival in rivals:
            aliases = _app_aliases(rival.name, names)
            if any(active in alias or alias in active for alias in aliases):
                chosen = rival
                break
    if chosen is None:
        return decision

    biased = decision.model_copy(deep=True)
    biased.target = {"type": "macro", "id": chosen.id.split(":", 1)[1]}
    logger.info(
        "[router] native app bias: %s -> %s (text=%r active=%s)",
        picked.name,
        chosen.name,
        text,
        active_app,
    )
    return biased


async def frontmost_app_name() -> str | None:
    """Live desktop context; None off-macOS / when indeterminate."""
    try:
        from app.infrastructure.drivers.macos._workspace import frontmost_application

        app = await asyncio.to_thread(frontmost_application)
        if app is None:
            return None
        return app.localizedName()
    except (ImportError, AttributeError, OSError, RuntimeError, ValueError):
        return None


async def bias_decisions(
    decisions: list[RouteDecision],
    candidates: list[RouteCandidate],
    text: str,
) -> list[RouteDecision]:
    """Bias a decision list in one pass; frontmost app probed lazily once."""
    needs_bias = any(
        d.status == "routed" and d.target_type == "macro" for d in decisions
    )
    if not needs_bias:
        return decisions
    active = await frontmost_app_name()
    return [apply_native_app_bias(d, candidates, text, active) for d in decisions]
