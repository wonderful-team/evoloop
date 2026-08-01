"""Reference Layer-0 local matcher (client matching spec, report §三十四).

The client does deterministic matching against RouteCatalog data; this is the
canonical backend implementation the client ports, and the artifact our
corpora validate. Five rules:

1. Anchored structural match — the whole utterance must BE the command
   (optional politeness affixes stripped). Declarative sentences containing
   trigger words ("下一首歌叫什么") fail the anchor structurally.
2. Longest-literal-first template order — subsumes "negative form first"
   ("取消静音" outranks "静音" by length; with anchoring this is belt and
   braces for clients that still substring-match during migration).
3. Slotted actions require slot verification against the shipped dictionaries
   (dual requirement: verb AND slot must both check out).
4. App-slot homophone fallback via pinyin EQUALITY (true homophones are
   distance 0; distance>=1 only buys false positives — weixin/weixing) with
   app_usage_rank as tiebreak. Latin app names (len>=4) allow edit distance 1.
5. (Subsumed by rule 1: the short-utterance length guard — an anchored match
   is already the whole utterance.)

Anything that fails to match returns None and falls back to the server
embedding+LLM path (conservative by design).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.routing.pinyin import to_pinyin

_PREFIXES = ("请", "帮我", "麻烦", "帮忙", "把", "给我")
_SUFFIXES = ("一下", "吧", "呀", "啊", "呗")
_APP_SUFFIX_NOISE = ("浏览器", "软件", "app", "APP", "App")

_AFFIX_RE = re.compile(
    rf"^(?:{'|'.join(_PREFIXES)})?(?P<body>.+?)(?:{'|'.join(_SUFFIXES)})?$"
)
_SLOT_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Map-slot containment leaves a remainder; it must be filler characters only,
# otherwise the utterance is a compound command ("把音量大一点再静音" captures
# delta="大一点再静音") and must fall through to Layer 1 WHOLE — half-executing
# one clause is worse than a plain false positive.
_SLOT_FILLER_CHARS: dict[str, frozenset[str]] = {
    "delta": frozenset("调给我到一点下把"),
    "key": frozenset("键一下"),
}


def _edit_distance_le1(a: str, b: str) -> bool:
    """True when edit distance <= 1 (only called on latin names, len>=4)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(c1 != c2 for c1, c2 in zip(a, b, strict=True)) == 1
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def _literal_len(pattern: str) -> int:
    return len(_SLOT_RE.sub("", pattern))


class LocalMatcher:
    """Deterministic Layer-0 matcher over RouteCatalog data."""

    def __init__(
        self,
        templates: list[dict[str, Any]],
        slot_dictionaries: dict[str, Any] | None = None,
        aliases: dict[str, str] | None = None,
        app_usage_rank: list[str] | None = None,
    ) -> None:
        self._dictionaries = slot_dictionaries or {}
        self._aliases = aliases or {}
        self._usage_rank = app_usage_rank or []
        self._compiled: list[tuple[re.Pattern[str], dict[str, Any], list[str], int]] = []
        for t in templates:
            for pattern in t.get("patterns", []):
                slots = _SLOT_RE.findall(pattern)
                body = re.escape(pattern)
                for slot in slots:
                    body = body.replace(r"\{" + slot + r"\}", f"(?P<{slot}>.+?)")
                anchored = re.compile(rf"^(?:{'|'.join(_PREFIXES)})?{body}(?:{'|'.join(_SUFFIXES)})?$")
                self._compiled.append((anchored, t, slots, _literal_len(pattern)))
        # Rule 2: longest literal first (per PATTERN, not per template — the
        # press_key template's "按下{key}" must outrank its own "按{key}").
        self._compiled.sort(key=lambda c: c[3], reverse=True)

    def match(self, text: str) -> tuple[str, dict[str, Any]] | None:
        cleaned = text.strip().strip("。，？！,.?! ")
        if not cleaned:
            return None
        for anchored, template, slots, _lit_len in self._compiled:
            m = anchored.match(cleaned)
            if not m:
                continue
            args = dict(template.get("args") or {})
            ok = True
            for slot in slots:
                value = m.group(slot)
                resolved = self._verify_slot(slot, value)
                if resolved is None:
                    ok = False
                    break
                args[slot] = resolved
            if ok:
                return template["action"], args
        return None

    # ── Rule 3/4: slot verification ───────────────────────────

    def _verify_slot(self, slot: str, value: str) -> str | None:
        if slot == "app":
            return self._verify_app(value)
        if slot in ("delta", "key"):
            return self._verify_from_dictionary(slot, value)
        return value  # free-text slots (e.g. rename.name)

    def _verify_app(self, value: str) -> str | None:
        cleaned = value
        for noise in _APP_SUFFIX_NOISE:
            if cleaned.endswith(noise) and len(cleaned) > len(noise):
                cleaned = cleaned[: -len(noise)]
        entries: list[dict[str, Any]] = self._dictionaries.get("app") or []
        names = [e.get("name", "") for e in entries if isinstance(e, dict)]

        for e in entries:
            if not isinstance(e, dict):
                continue
            if cleaned == e.get("name") or cleaned in (e.get("aliases") or []):
                return self._canonical(e["name"])

        # Global alias lookup (e.g., 微信 -> WeChat, 浏览器 -> Safari) when the
        # spoken alias is not listed as an entry alias but maps to a canonical
        # app name that IS installed.
        canonical = self._aliases.get(cleaned)
        if canonical:
            for e in entries:
                if not isinstance(e, dict):
                    continue
                if canonical == e.get("name") or canonical in (e.get("aliases") or []):
                    return self._canonical(canonical)

        cleaned_py = to_pinyin(cleaned)
        if cleaned_py:
            candidates = []
            for e in entries:
                if not isinstance(e, dict):
                    continue
                entry_py = e.get("pinyin") or to_pinyin(e.get("name", ""))
                if entry_py and entry_py == cleaned_py:
                    candidates.append(e["name"])
            if candidates:
                best = min(
                    candidates,
                    key=lambda n: self._usage_rank.index(n) if n in self._usage_rank else len(self._usage_rank),
                )
                return self._canonical(best)

        if cleaned.isascii() and len(cleaned) >= 4:
            for name in names:
                if name.isascii() and len(name) >= 4 and _edit_distance_le1(cleaned.lower(), name.lower()):
                    return self._canonical(name)
        return None

    def _verify_from_dictionary(self, slot: str, value: str) -> str | None:
        dictionary: dict[str, str] = self._dictionaries.get(slot) or {}
        if value in dictionary:
            return dictionary[value]
        filler = _SLOT_FILLER_CHARS.get(slot)
        for key in sorted(dictionary, key=len, reverse=True):
            if key not in value:
                continue
            if filler is not None:
                remainder = value.replace(key, "", 1)
                if any(ch not in filler for ch in remainder):
                    continue  # dirty remainder: compound command, try shorter keys
            return dictionary[key]
        return None

    def _canonical(self, name: str) -> str:
        return self._aliases.get(name, name)


def sorted_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rule 2 shipping order: longest-literal patterns first."""
    return sorted(
        templates,
        key=lambda t: max((_literal_len(p) for p in t.get("patterns", [])), default=0),
        reverse=True,
    )
