"""Macro resolution for BERT intent candidates.

Loads routable macros from the database, normalizes trigger patterns, extracts
slot values, and returns a resolved ``("macro:{id}", args)`` tuple.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.routing.routing_data import RoutingLanguageStore, get_store
from app.models.macro import Macro
from app.utils.text import strip_filler_words

logger = logging.getLogger(__name__)


def _normalize_trigger_patterns(macro: Macro) -> list[str]:
    """Return trigger_patterns as a list of strings."""
    patterns = macro.trigger_patterns
    if isinstance(patterns, str):
        try:
            patterns = json.loads(patterns)
        except (json.JSONDecodeError, TypeError):
            patterns = []
    if isinstance(patterns, list):
        return [p for p in patterns if isinstance(p, str)]
    return []


def _extract_slots(
    intent_name: str, text: str, slot_prefixes: list[str]
) -> dict[str, str]:
    """Simple slot extraction from raw text by stripping known prefixes."""
    del intent_name  # kept for API symmetry; actual extraction is prefix-based
    for prefix in slot_prefixes:
        if text.startswith(prefix):
            return {"_value": text[len(prefix) :].strip(), "_text": text}
    return {}


class MacroResolver:
    """Resolve BERT intent candidates against DB macros."""

    def __init__(self, routing_store: RoutingLanguageStore | None = None) -> None:
        self._routing_store = routing_store or get_store()

    async def _list_macros_by_name(self, name: str, project_id: int) -> list[Macro]:
        """Load all verified, active macros by name, scoped to ``project_id``.

        Ordered project-first, then preset-first, then newest-first
        (``created_at`` desc), so that the most recently confirmed macro wins
        when multiple macros share the same intent label or trigger pattern.
        This keeps runtime resolution consistent with the Init Spec (which
        also keeps the newest macro for a repeated pattern).
        """
        from app.core.learning.macro.service import MacroService

        macros = await MacroService.list_routable_macros(project_id=project_id)
        return [
            m
            for m in macros
            if m.name == name and (m.project_id is None or m.project_id == project_id)
        ]

    def _extract_slot_name(self, macro: Macro) -> str | None:
        """Return the first slot name declared by the macro, if any."""
        if not macro.parameters:
            return None
        try:
            plist = (
                json.loads(macro.parameters)
                if isinstance(macro.parameters, str)
                else macro.parameters
            )
            if isinstance(plist, list) and plist:
                return plist[0].get("name")
        except (json.JSONDecodeError, TypeError, IndexError):
            pass
        return None

    def _build_args(
        self,
        macro: Macro,
        text: str,
        slot_val: str,
        slot_name: str | None,
    ) -> dict[str, Any]:
        """Build macro arguments from a matched slot value or prefix extraction."""
        args: dict[str, Any] = {}
        if slot_val and slot_name:
            args[slot_name] = slot_val.strip()
        elif slot_name:
            slots = _extract_slots(macro.name, text, self._routing_store.slot_prefixes)
            if "_value" in slots:
                args[slot_name] = slots["_value"]
        return args

    def _build_pattern_regex(self, pattern: str, slot_name: str | None) -> str:
        """Return a full-match regex that tolerates optional whitespace between tokens.

        Voice input often contains spaces between action verbs and slots (e.g.
        ``启动 Safari`` or ``关闭 WiFi``).  We insert ``\\s*`` between every
        pair of literal characters so the stored trigger patterns still match
        spaced utterances without requiring every macro to list every spacing
        variant.
        """
        marker = "\x00SLOT\x00"
        temp = pattern.replace(f"{{{slot_name}}}", marker) if slot_name else pattern

        tokens: list[str] = []
        i = 0
        while i < len(temp):
            if temp.startswith(marker, i):
                tokens.append(marker)
                i += len(marker)
            else:
                tokens.append(temp[i])
                i += 1

        parts: list[str] = []
        for idx, token in enumerate(tokens):
            if token == marker:
                parts.append(r"(.+)")
            else:
                parts.append(re.escape(token))
            if idx < len(tokens) - 1 and token != marker and tokens[idx + 1] != marker:
                parts.append(r"\s*")
        return "^" + "".join(parts) + "$"

    async def resolve(
        self,
        candidates: list[str],
        text: str,
        project_id: int,
    ) -> tuple[str, dict[str, Any]] | None:
        """Try each candidate name against DB macros.

        L0 是动作分类器主导的路由：候选名（BERT 意图标签）一旦命中对应宏，
        就应以意图名命中该宏，触发词仅用于槽位提取，不作为命中门槛。

        Returns ``("macro:{macro.id}", args)`` on the first match, or ``None``
        if no macro accepts the text.
        """
        for name in candidates:
            macros = await self._list_macros_by_name(name, project_id)
            for macro in macros:
                patterns = _normalize_trigger_patterns(macro)
                slot_name = self._extract_slot_name(macro)

                # 1) 快速路径：触发词全匹配（槽位提取精准）。
                #    优先对"去填充词"后的文本匹配（槽位值干净，不把"一下"等口语词
                #    吃进槽位），miss 再回退原文匹配（兼容"把{app}打开"类含填充词的
                #    触发词）。两种都失败才进入宽松槽位提取。
                for text_variant in (self._strip_fillers(text), text):
                    slot_val = ""
                    matched = False
                    for pattern in patterns:
                        regex_str = self._build_pattern_regex(pattern, slot_name)
                        match = re.fullmatch(regex_str, text_variant, re.IGNORECASE)
                        if match:
                            matched = True
                            # pattern 可能未含 {slot} 占位符（宏声明了参数但触发词
                            # 未引用它）→ 正则无捕获组，group(1) 会 IndexError。
                            slot_val = match.group(1) if match.groups() else ""
                            break
                    if matched:
                        if slot_val:
                            slot_val = strip_filler_words(
                                slot_val,
                                self._routing_store.slot_filler_prefixes,
                                self._routing_store.slot_filler_suffixes,
                            )
                        args = self._build_args(macro, text, slot_val, slot_name)
                        return f"macro:{macro.id}", args

                # 2) 兜底：动作分类器已给出意图名 → 意图名命中该宏。
                #    触发词不再作为命中门槛，仅用于宽松槽位提取。
                args = self._resolve_args_loose(macro, text, slot_name)
                if args is not None:
                    return f"macro:{macro.id}", args

        return None

    def _strip_fillers(self, text: str) -> str:
        """去口语填充词（单前缀 + 后缀），与 local_matcher 词表一致（数据化）。"""
        t = text.strip()
        for p in sorted(self._routing_store.polite_prefixes, key=len, reverse=True):
            if t.startswith(p):
                t = t[len(p) :].strip()
                break
        for s in sorted(self._routing_store.polite_suffixes, key=len, reverse=True):
            if t.endswith(s):
                t = t[: -len(s)].strip()
        return t

    def _resolve_args_loose(
        self, macro: Macro, text: str, slot_name: str | None
    ) -> dict[str, Any] | None:
        """意图名命中后做宽松槽位提取。

        无参数宏直接命中（返回 {}）；参数化宏需要能从文本中提取到槽位值，
        否则返回 None 保守跳过（避免 required 参数缺失导致执行失败）。
        """
        if not slot_name:
            return {}
        cleaned = self._strip_fillers(text)
        if not cleaned:
            return None
        patterns = _normalize_trigger_patterns(macro)
        for pattern in patterns:
            if f"{{{slot_name}}}" not in pattern:
                continue
            full = self._build_pattern_regex(pattern, slot_name)
            loose = full[1:-1]  # 去掉锚定 ^$，在 cleaned 内 search
            m = re.search(loose, cleaned, re.IGNORECASE)
            if not m:
                continue
            val = strip_filler_words(
                m.group(1),
                self._routing_store.slot_filler_prefixes,
                self._routing_store.slot_filler_suffixes,
            )
            if val and not self._is_noise_slot(val):
                return {slot_name: val}
        return None

    def _is_noise_slot(self, value: str) -> bool:
        """拒绝无意义的槽位值（口语指代/填充），避免误提。

        词表数据化复用 ``free_text_reject_markers``（与 LocalMatcher 一致）。
        """
        return any(marker in value for marker in self._routing_store.free_text_reject_markers)


__all__ = ["MacroResolver"]
