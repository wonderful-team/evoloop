"""Macro resolution for BERT intent candidates.

Loads routable macros from the database, normalizes trigger patterns, extracts
slot values, and returns a resolved ``("macro:{id}", args)`` tuple.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import case
from sqlmodel import select

from app.core.routing.routing_data import RoutingLanguageStore, get_store
from app.infrastructure.database import session_scope
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


def _extract_slots(intent_name: str, text: str, slot_prefixes: list[str]) -> dict[str, str]:
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

    async def _load_macro_by_name(self, name: str, project_id: int) -> Macro | None:
        """Load a verified, active macro by name, scoped to ``project_id``."""
        async with session_scope() as session:
            stmt = (
                select(Macro)
                .where(
                    Macro.name == name,
                    Macro.is_active.is_(True),
                    Macro.status == "verified",
                    (Macro.project_id.is_(None)) | (Macro.project_id == project_id),
                )
                .order_by(
                    case((Macro.namespace == "preset", 0), else_=1),
                    Macro.created_at.asc(),
                )
            )
            result = await session.execute(stmt)
            macro = result.scalars().first()
        return macro

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

        Returns ``("macro:{macro.id}", args)`` on the first match, or ``None``
        if no macro accepts the text.
        """
        for name in candidates:
            macro = await self._load_macro_by_name(name, project_id)
            if macro is None:
                continue

            patterns = _normalize_trigger_patterns(macro)
            slot_name = self._extract_slot_name(macro)
            matched = False
            slot_val = ""

            if patterns:
                for pattern in patterns:
                    regex_str = self._build_pattern_regex(pattern, slot_name)
                    match = re.fullmatch(regex_str, text, re.IGNORECASE)
                    if match:
                        matched = True
                        slot_val = match.group(1) if slot_name else ""
                        break
                if not matched:
                    logger.info(
                        "[macro_resolver] BERT predicted candidate %r but text %r "
                        "doesn't match macro %d patterns, rejecting",
                        name,
                        text,
                        macro.id,
                    )
                    continue

            args = self._build_args(macro, text, slot_val, slot_name)
            return f"macro:{macro.id}", args

        return None


__all__ = ["MacroResolver"]
