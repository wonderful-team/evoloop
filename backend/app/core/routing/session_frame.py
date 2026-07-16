"""Conversation-scoped session frame for multi-turn voice routing.

Lives exactly as long as the conversation (thread_id) — volatile in-memory,
no persistence, no TTL strategy (per design decision: multi-turn is only
supported inside a continuous conversation; when it ends the frame is
discarded). The frame answers two questions for the NEXT utterance:

  - current_page: where the browser is (skip redundant navigation)
  - current_entity: what we were just talking about (anaphora: 它/这个)
  - pending: an unanswered clarify question (missing entity) — the next
    utterance in this conversation is treated as its answer
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

_TTL_SECONDS = 1800  # safety net only; normal teardown is explicit clear()
_UNSET: Any = object()  # distinguishes "leave pending" from "clear pending"


@dataclass
class SessionFrame:
    current_page: str | None = None
    current_entity: dict[str, Any] | None = None  # {query, entity_id, macro_id, value}
    pending: dict[str, Any] | None = None  # {kind: "missing_entity", text: str}
    updated_at: float = field(default_factory=time.monotonic)


_FRAMES: dict[str, SessionFrame] = {}


def get_frame(thread_id: str) -> SessionFrame | None:
    frame = _FRAMES.get(thread_id)
    if frame is None:
        return None
    if time.monotonic() - frame.updated_at > _TTL_SECONDS:
        _FRAMES.pop(thread_id, None)
        return None
    return frame


def update_frame(
    thread_id: str,
    *,
    current_page: str | None = None,
    current_entity: dict[str, Any] | None = None,
    pending: Any = _UNSET,
) -> SessionFrame:
    frame = _FRAMES.get(thread_id) or SessionFrame()
    if current_page is not None:
        frame.current_page = current_page
    if current_entity is not None:
        frame.current_entity = current_entity
    if pending is not _UNSET:
        frame.pending = pending
    frame.updated_at = time.monotonic()
    _FRAMES[thread_id] = frame
    return frame


def clear_frame(thread_id: str) -> None:
    _FRAMES.pop(thread_id, None)


# Longest-first so compounds win over 这个. Bare 该/此 are excluded — 应该/因此
# would false-positive. Bare 它/他/她 REQUIRE context (preceded by 把/将/给/
# 让/对/向 or followed by 的): entity names contain these characters as
# ordinary morphemes (吉他/维他奶/维也纳/其他) and blind substitution would
# CORRUPT the utterance instead of degrading conservatively. Only the FIRST
# token is rewritten (one referent per utterance is the voice norm).
#
# 语言框架(这个/那个/该/此/把/将/给…)写死;领域名词(商品/订单/会员…)是业务
# 数据,NOT linguistic —— 由 set_domain_nouns() 从 AppMap 别名注入(换行业后台
# 时名词集随之切换),缺省时复合词组退化为裸 这个/那个/这件。
_DOMAIN_NOUNS: frozenset[str] = frozenset()


def _build_anaphora_re() -> re.Pattern[str]:
    compounds = ""
    if _DOMAIN_NOUNS:
        alt = "|".join(
            sorted((re.escape(n) for n in _DOMAIN_NOUNS), key=len, reverse=True)
        )
        compounds = rf"(?:这个|那个|该|此|这件)(?:{alt})|"
    return re.compile(
        compounds
        + r"这个|那个|这件"
        + r"|(?<=[把将给让对向])[他她它]"
        + r"|(?<![吉维其])[他她它](?=的)"  # 吉他/维他奶/维也纳/其他 的"他"不是指代
    )


_ANAPHORA_RE = _build_anaphora_re()


def set_domain_nouns(nouns: list[str] | set[str] | frozenset[str]) -> None:
    """Inject the business-domain noun set (AppMap entity CJK aliases).

    Called by routing.sync on index rebuild; the anaphora regex is rebuilt
    so compounds like 这个订单/该会员 resolve in any industry backend.
    """
    global _DOMAIN_NOUNS, _ANAPHORA_RE
    _DOMAIN_NOUNS = frozenset(nouns)
    _ANAPHORA_RE = _build_anaphora_re()


def resolve_anaphora(text: str, frame: SessionFrame | None) -> str:
    """Rewrite '把它的库存改成142' using the frame's current entity.

    Deterministic string substitution — the frame's `query` is the exact
    search phrase that worked last turn, so the rewritten text routes and
    executes identically to a fully-specified utterance.
    """
    if frame is None or not frame.current_entity:
        return text
    query = frame.current_entity.get("query")
    if not query or query in text:
        return text
    m = _ANAPHORA_RE.search(text)
    if m is None:
        return text
    return text[: m.start()] + query + text[m.end():]


def has_anaphora(text: str) -> bool:
    return _ANAPHORA_RE.search(text) is not None


_CONNECTOR_RE = re.compile(r"，|,|；|;|然后|接着|并且|再一|之后再|然后再")


_CONTEXT_SWITCH_RE = re.compile(
    r"^(?:那?(?:换成|换|要|改)|(?:另一个|别的|换一个|改查))"
)


def has_connector(text: str) -> bool:
    return _CONNECTOR_RE.search(text) is not None


def normalize_context_switch(text: str) -> tuple[str, bool]:
    """Detect and strip context-switching prefixes (e.g. '那换成查X' -> '查X').

    Returns the normalized text and a flag indicating whether a switch was
    detected. The router uses the flag to discard the stale session frame
    so the new entity is not contaminated by the previous turn's referent.
    """
    m = _CONTEXT_SWITCH_RE.match(text)
    if not m:
        return text, False
    body = text[m.end():].lstrip("，,、 \t")
    return body, True


def clarify_question(text: str) -> str:
    """Deterministic 'which one?' phrasing keyed on the utterance's domain."""
    if "订单" in text:
        return "请问是哪个订单？"
    if any(k in text for k in ("商品", "库存", "价格", "售价")):
        return "请问是哪个商品？"
    return "请问你指的是哪个？"


def consume_pending(text: str, frame: SessionFrame | None) -> tuple[str, bool]:
    """If the frame holds an unanswered clarify question, treat THIS utterance
    as the answer and splice it into the pending text.

    '把它的库存改成142' + answer '夜光亚克力钥匙扣' ->
    '把夜光亚克力钥匙扣的库存改成142'. When the pending text has no anaphora
    token (bare '改库存到142'), the answer is prefixed instead.
    """
    if frame is None or not frame.pending:
        return text, False
    pending = frame.pending
    frame.pending = None  # consumed regardless of what the answer contains
    if pending.get("kind") != "missing_entity":
        return text, False
    answer = text.strip().strip("。，,.?？!！ ")
    if not answer:
        return text, False
    ptext = pending.get("text") or ""
    m = _ANAPHORA_RE.search(ptext)
    combined = (
        ptext[: m.start()] + answer + ptext[m.end():]
        if m
        else f"{answer}，{ptext}"
    )
    return combined, True
