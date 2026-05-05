"""
Domain Term Bank — Agent self-maintained per-project terminology.

Storage structure (v3 — LLM-driven extraction, no regex/n-gram):
    {
      "terms": {
        "心室颤动": {"freq": 5, "last_seen": "2026-04-29T14:32:28"},
        "api gateway": {"freq": 3, "last_seen": "2026-04-29T14:32:28"}
      }
    }

Design principles:
- Term extraction is performed by LLM, not regex/n-gram heuristics
- No admission gates, no staging cache, no stopword filters
- Terms are persisted immediately upon LLM extraction
- Confidence is computed at runtime from freq + temporal decay
"""

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from app.utils import render_template

logger = logging.getLogger(__name__)

# Runtime confidence params
_MIN_TERM_CONFIDENCE = 0.15
_MAX_TERM_CONFIDENCE = 1.0
_MAX_TERMS_PER_EXTRACTION = 5


class TermMeta:
    """Lightweight metadata for a single domain term.

    v3: only freq + last_seen persisted; confidence computed at runtime.
    """

    __slots__ = ("freq", "last_seen")

    def __init__(self, freq: int = 0, last_seen: datetime | None = None):
        self.freq = freq
        self.last_seen = last_seen or datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "freq": self.freq,
            "last_seen": self.last_seen.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TermMeta":
        return cls(
            freq=d.get("freq", 0),
            last_seen=datetime.fromisoformat(d["last_seen"]),
        )


class DomainTermBank:
    """
    Per-project terminology library maintained by LLM extraction.

    Storage layout:
        ~/.evoloop/memory/domain_terms/
            _global.json          # fallback when project_id is None
            {project_id}.json     # project-specific term banks

    Usage:
        bank = DomainTermBank("/path/to/memory/domain_terms")
        await bank.discover(content, project_id=42, project_context="...")
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
                k: TermMeta.from_dict(v)
                for k, v in data.get("terms", {}).items()
            }
        except Exception as e:
            logger.warning(f"[TermBank] Failed to load {path}: {e}")
            return {}

    async def _save(self, project_id: int | None, terms: dict[str, TermMeta]) -> None:
        path = self._project_path(project_id)
        payload = {"terms": {k: v.to_dict() for k, v in terms.items()}}
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
    def _compute_confidence(
        freq: int,
        last_seen: datetime,
        half_life_days: int = 30,
    ) -> float:
        """Compute term confidence from frequency and temporal decay."""
        days = (datetime.now(timezone.utc) - last_seen).total_seconds() / 86400
        decay = 0.5 ** (days / half_life_days)
        base = min(0.3 + freq * 0.05, 0.95)
        return round(base * decay, 4)

    @staticmethod
    def _parse_llm_response(content: str) -> list[str]:
        """Extract JSON array of terms from LLM response."""
        # Try to find JSON array in the response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if not match:
            return []
        try:
            terms = json.loads(match.group())
            if isinstance(terms, list):
                # Filter: strings only, non-empty, reasonable length
                return [
                    str(t).strip()
                    for t in terms
                    if isinstance(t, (str,)) and str(t).strip()
                ]
        except json.JSONDecodeError:
            logger.debug(f"[TermBank] Failed to parse LLM response: {content[:200]}")
        return []

    async def _extract_with_llm(
        self,
        content: str,
        project_context: str,
        max_terms: int = _MAX_TERMS_PER_EXTRACTION,
    ) -> list[str]:
        """Call LLM to extract domain terms from content."""
        from app.infrastructure.config.service import SystemConfigService
        from app.core.llm import InternalLLMService

        model_name = SystemConfigService.get_value("LLM_MODEL")
        if not model_name:
            logger.warning("[TermBank] No LLM model configured, skipping term extraction")
            return []

        prompt = render_template(
            "core/memory/term_extraction.prompt.j2",
            content=content,
            project_context=project_context,
            max_terms=max_terms,
        )

        messages = [
            {"role": "system", "content": "You are a precise domain terminology extractor."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await InternalLLMService.invoke(
                messages=messages,
                purpose="domain_term_extraction",
                temperature=0.3,
                max_tokens=300,
                model_name=model_name,
            )
            terms = self._parse_llm_response(response.content)
            logger.debug(f"[TermBank] LLM extracted {len(terms)} terms: {terms}")
            return terms
        except Exception as e:
            logger.warning(f"[TermBank] LLM term extraction failed: {e}")
            return []

    # ── Public API ────────────────────────────────────────────────────

    async def get_terms(self, project_id: int | None) -> dict[str, TermMeta]:
        """Return all persisted terms for a project (or global)."""
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
        project_context: str = "",
    ) -> list[str]:
        """
        Extract domain terms from content via LLM and update the term bank.

        Terms are persisted immediately (no staging, no frequency threshold).
        project_context should contain PROJECT.md or other project background.
        """
        if not content or not content.strip():
            return []

        terms = await self._extract_with_llm(content, project_context)
        if not terms:
            return []

        now = datetime.now(timezone.utc)

        async with self._lock:
            persisted = await self._load(project_id)
            for term in terms:
                if term in persisted:
                    persisted[term].freq += 1
                    persisted[term].last_seen = now
                else:
                    persisted[term] = TermMeta(freq=1, last_seen=now)
            await self._save(project_id, persisted)

        return terms

    async def decay(
        self,
        project_id: int | None,
        half_life_days: int = 30,
    ) -> list[str]:
        """
        Apply temporal decay to all terms. Terms falling below threshold are removed.

        Confidence is computed at runtime from freq and last_seen.
        Returns list of removed term strings.
        """
        async with self._lock:
            terms = await self._load(project_id)
            if not terms:
                return []

            removed: list[str] = []
            survivors: dict[str, TermMeta] = {}

            for token, meta in terms.items():
                confidence = self._compute_confidence(
                    meta.freq, meta.last_seen, half_life_days
                )
                if confidence < _MIN_TERM_CONFIDENCE:
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
        Confidence is computed at runtime from freq and last_seen.
        """
        terms = await self.get_terms(project_id)
        if not terms:
            terms = await self.get_terms(project_id=None)
        scored = []
        for token, meta in terms.items():
            confidence = self._compute_confidence(meta.freq, meta.last_seen)
            if confidence >= min_confidence:
                score = confidence * (1 + math.log(meta.freq + 1))
                scored.append((token, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [token for token, _ in scored[:limit]]
