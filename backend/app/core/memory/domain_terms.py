"""
Domain Term Bank — Agent self-maintained per-project terminology.

No external NLP dependencies. Uses simple regex tokenization + frequency tracking.
Terms are stored as independent JSON files (not MemoryEntry) for lightweight R/W.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.memory.stopwords import ALL_STOPWORDS

logger = logging.getLogger(__name__)

# ── Tokenization regexes ──────────────────────────────────────────────
_EN_WORD_RE = re.compile(r"\b[a-zA-Z]{2,}\b")
_ZH_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_EN_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+\b")
_PURE_NUM_RE = re.compile(r"^\d+$")

# Minimum confidence for a term to be considered "known"
_MIN_TERM_CONFIDENCE = 0.15

# Confidence boost for a term discovered in a high-quality memory
_DISCOVERY_BOOST = 0.05

# Maximum confidence cap for any term
_MAX_TERM_CONFIDENCE = 1.0


class TermMeta(BaseModel):
    """Metadata for a single domain term."""

    lang: str = "en"  # "en" | "zh" | "mixed"
    freq: int = 0
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0
    aliases: list[str] = Field(default_factory=list)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(**kwargs)
        # Ensure datetime is ISO string for JSON serialization
        if isinstance(d.get("last_seen"), datetime):
            d["last_seen"] = d["last_seen"].isoformat()
        return d


class DomainTermBank:
    """
    Per-project terminology library that Agent maintains automatically.

    Storage layout:
        ~/.evoloop/memory/domain_terms/
            _global.json          # fallback when project_id is None
            {project_id}.json     # project-specific term banks

    Usage:
        bank = DomainTermBank("/path/to/memory/domain_terms")
        await bank.discover(content, project_id=42, memory_confidence=0.8)
        matched = await bank.match(content, project_id=42)
        top = await bank.get_top_terms(project_id=42, limit=20)
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._global_path = self._base_path / "_global.json"
        self._lock = asyncio.Lock()

    # ── Internal helpers ──────────────────────────────────────────────

    def _project_path(self, project_id: int | None) -> Path:
        if project_id is None:
            return self._global_path
        return self._base_path / f"{project_id}.json"

    async def _load(self, project_id: int | None) -> dict[str, TermMeta]:
        path = self._project_path(project_id)
        if not path.exists():
            return {}

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(None, path.read_text, "utf-8")
            data = json.loads(raw)
            return {
                k: TermMeta(**v)
                for k, v in data.get("terms", {}).items()
            }
        except Exception as e:
            logger.warning(f"[TermBank] Failed to load {path}: {e}")
            return {}

    async def _save(self, project_id: int | None, terms: dict[str, TermMeta]) -> None:
        path = self._project_path(project_id)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "terms": {k: v.model_dump() for k, v in terms.items()},
        }
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                ),
            )
        except Exception as e:
            logger.warning(f"[TermBank] Failed to save {path}: {e}")

    @staticmethod
    def _extract_tokens(content: str) -> dict[str, int]:
        """Extract candidate term tokens from content with frequency counts."""
        counts: dict[str, int] = {}

        # 1. English words (2+ chars)
        for w in _EN_WORD_RE.findall(content):
            w_lower = w.lower()
            if w_lower in ALL_STOPWORDS or _PURE_NUM_RE.match(w_lower):
                continue
            counts[w_lower] = counts.get(w_lower, 0) + 1

        # 2. Chinese phrases — whole phrase + 2-4 char n-grams
        for phrase in _ZH_WORD_RE.findall(content):
            if phrase not in ALL_STOPWORDS:
                counts[phrase] = counts.get(phrase, 0) + 1
            # Extract 2-4 char substrings (covers most Chinese terms)
            if len(phrase) >= 2:
                max_n = min(5, len(phrase) + 1)
                for n in range(2, max_n):
                    for i in range(len(phrase) - n + 1):
                        sub = phrase[i:i + n]
                        if sub not in ALL_STOPWORDS:
                            counts[sub] = counts.get(sub, 0) + 1

        # 3. English proper noun phrases (API Gateway, Data Model, ...)
        for phrase in _EN_PROPER_RE.findall(content):
            words = phrase.lower().split()
            words = [w for w in words if w not in ALL_STOPWORDS]
            if len(words) >= 2:
                normalized = " ".join(words)
                counts[normalized] = counts.get(normalized, 0) + 1

        return counts

    @staticmethod
    def _detect_lang(token: str) -> str:
        if any("\u4e00" <= ch <= "\u9fff" for ch in token):
            return "zh"
        return "en"

    # ── Public API ────────────────────────────────────────────────────

    async def get_terms(self, project_id: int | None) -> dict[str, TermMeta]:
        """Return all terms for a project (or global)."""
        async with self._lock:
            return await self._load(project_id)

    async def match(self, content: str, project_id: int | None) -> list[str]:
        """Return list of known terms that appear in content.

        Falls back to global terms if project-specific bank is empty.
        """
        terms = await self.get_terms(project_id)
        if not terms:
            terms = await self.get_terms(project_id=None)
        if not terms:
            return []

        content_lower = content.lower()
        matched = []
        for term in terms:
            if term.lower() in content_lower:
                matched.append(term)
        return matched

    async def discover(
        self,
        content: str,
        project_id: int | None,
        memory_confidence: float = 0.5,
    ) -> None:
        """
        Extract candidate terms from content and update the term bank.

        Only terms from memories with confidence >= 0.5 are considered reliable
        enough to contribute to the bank.
        """
        if memory_confidence < 0.5:
            return

        tokens = self._extract_tokens(content)
        if not tokens:
            return

        async with self._lock:
            terms = await self._load(project_id)
            now = datetime.now(timezone.utc)

            for token, count in tokens.items():
                if token not in terms:
                    terms[token] = TermMeta(
                        lang=self._detect_lang(token),
                        freq=count,
                        last_seen=now,
                        confidence=min(
                            _DISCOVERY_BOOST * memory_confidence + 0.3,
                            _MAX_TERM_CONFIDENCE,
                        ),
                    )
                else:
                    meta = terms[token]
                    meta.freq += count
                    meta.last_seen = now
                    meta.confidence = min(
                        meta.confidence + _DISCOVERY_BOOST * memory_confidence,
                        _MAX_TERM_CONFIDENCE,
                    )

            await self._save(project_id, terms)

    async def decay(
        self,
        project_id: int | None,
        half_life_days: int = 30,
    ) -> list[str]:
        """
        Apply temporal decay to all terms. Terms falling below threshold are removed.

        Returns list of removed term strings.
        """
        async with self._lock:
            terms = await self._load(project_id)
            if not terms:
                return []

            now = datetime.now(timezone.utc)
            removed: list[str] = []
            survivors: dict[str, TermMeta] = {}

            for token, meta in terms.items():
                days = (now - meta.last_seen).total_seconds() / 86400
                # Exponential decay
                meta.confidence *= 0.5 ** (days / half_life_days)

                if meta.confidence < _MIN_TERM_CONFIDENCE:
                    removed.append(token)
                else:
                    survivors[token] = meta

            if removed:
                logger.info(
                    f"[TermBank] Decayed {len(removed)} stale terms "
                    f"(project={project_id})"
                )
                await self._save(project_id, survivors)

            return removed

    async def get_top_terms(
        self,
        project_id: int | None,
        limit: int = 20,
        min_confidence: float = 0.3,
    ) -> list[str]:
        """Return top-N terms sorted by confidence * log(freq).

        Falls back to global terms if project-specific bank is empty.
        """
        terms = await self.get_terms(project_id)
        if not terms:
            terms = await self.get_terms(project_id=None)
        scored = [
            (token, meta.confidence * (1 + __import__("math").log(meta.freq + 1)))
            for token, meta in terms.items()
            if meta.confidence >= min_confidence
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [token for token, _ in scored[:limit]]
