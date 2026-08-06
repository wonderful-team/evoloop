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
from app.utils.text import strip_filler_words

# 口语填充词仅来自路由数据（templates.yaml），无代码侧兜底：未配置即为空。

# 口语填充词可叠加：多个前缀连续出现时全部剥离（"帮我把窗口左分屏" → "窗口左分屏"）。
_SLOT_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Map-slot containment leaves a remainder; it must be filler characters only,
# otherwise the utterance is a compound command ("把音量大一点再静音" captures
# delta="大一点再静音") and must fall through to Layer 1 WHOLE — half-executing
# one clause is worse than a plain false positive.
# 余料字符表（按 slot 名）来自路由数据 templates.yaml 的 slot_filler_chars。


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
        polite_prefixes: list[str] | None = None,
        polite_suffixes: list[str] | None = None,
        slot_filler_prefixes: list[str] | None = None,
        slot_filler_suffixes: list[str] | None = None,
        app_suffix_noise: list[str] | None = None,
        free_text_reject_markers: list[str] | None = None,
        slot_filler_chars: dict[str, str] | None = None,
    ) -> None:
        self._dictionaries = slot_dictionaries or {}
        self._aliases = aliases or {}
        self._usage_rank = app_usage_rank or []
        # 口语填充词仅取路由数据（templates.yaml）单一来源，无代码兜底默认。
        self._prefixes: tuple[str, ...] = tuple(polite_prefixes or ())
        self._suffixes: tuple[str, ...] = tuple(polite_suffixes or ())
        # 槽位值清洗词（数据化），提取 slot 值后剥离口语填充
        self._slot_filler_prefixes: tuple[str, ...] = tuple(slot_filler_prefixes or ())
        self._slot_filler_suffixes: tuple[str, ...] = tuple(slot_filler_suffixes or ())
        # 应用名后缀噪声 / 自由文本槽位拒绝词 / 槽位余料字符（皆数据化）
        self._app_suffix_noise: tuple[str, ...] = tuple(app_suffix_noise or ())
        self._free_text_reject_markers: tuple[str, ...] = tuple(
            free_text_reject_markers or ()
        )
        self._free_text_reject: frozenset[str] = frozenset(
            free_text_reject_markers or ()
        )
        self._slot_filler_chars: dict[str, str] = slot_filler_chars or {}
        self._compiled: list[tuple[re.Pattern[str], dict[str, Any], list[str], int]] = []
        for t in templates:
            for pattern in t.get("patterns", []):
                slots = _SLOT_RE.findall(pattern)
                body = re.escape(pattern)
                for slot in slots:
                    body = body.replace(r"\{" + slot + r"\}", f"(?P<{slot}>.+?)")
                anchored = re.compile(rf"^(?:{'|'.join(self._prefixes)})?{body}(?:{'|'.join(self._suffixes)})?$")
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
                args[slot] = strip_filler_words(resolved, self._slot_filler_prefixes, self._slot_filler_suffixes)
            if ok:
                return template["action"], args
        return None

    # ── Rule 3/4: slot verification ───────────────────────────

    def _verify_slot(self, slot: str, value: str) -> str | None:
        if slot == "app":
            return self._verify_app(value)
        if slot in ("delta", "key"):
            return self._verify_from_dictionary(slot, value)
        # Free-text slots: reject deictic/hedge tokens and any value that names
        # an app (exact name, alias, or pinyin-homophone).  Such a value almost
        # always means the app slot template (or the BERT fallback) owns the
        # utterance, not this free-text slot.
        if value in self._free_text_reject or any(
            m in value for m in self._free_text_reject_markers
        ):
            return None
        if self._verify_app(value) is not None:
            return None
        return value  # free-text slots (e.g. rename.name)

    def _verify_app(self, value: str) -> str | None:
        cleaned = value
        for noise in self._app_suffix_noise:
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
                    key=lambda n: (
                        self._usage_rank.index(n)
                        if n in self._usage_rank else len(self._usage_rank)
                    ),
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
        filler = self._slot_filler_chars.get(slot)
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
