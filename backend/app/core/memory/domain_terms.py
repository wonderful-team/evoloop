"""
Domain Term Bank — Agent self-maintained per-project terminology.

No external NLP dependencies. Uses simple regex tokenization + frequency tracking.
Terms are stored as independent JSON files (not MemoryEntry) for lightweight R/W.

Storage structure (v2, simplified):
    {
      "terms": {
        "心室颤动": {"freq": 5, "last_seen": "2026-04-29T14:32:28", "confidence": 0.8234},
        "api gateway": {"freq": 3, "last_seen": "2026-04-29T14:32:28", "confidence": 0.7123}
      }
    }

Admission policy:
- freq >= 2 before persisting (first sight kept in memory cache only)
- Chinese: whole phrase 2-6 chars; n-grams 2-4 chars, no stopwords inside
- English: single words >=3 chars, exclude common generic verbs;
           multi-word proper nouns kept as-is
- All confidence values rounded to 4 decimals on save
"""

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core.memory.stopwords import ALL_STOPWORDS

logger = logging.getLogger(__name__)

# ── Tokenization regexes ──────────────────────────────────────────────
_EN_WORD_RE = re.compile(r"\b[a-zA-Z]{2,}\b")
_ZH_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_EN_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+\b")
_PURE_NUM_RE = re.compile(r"^\d+$")

# Common generic English verbs — too frequent to be domain-specific terms
_EN_GENERIC_VERBS: set[str] = {
    "use", "used", "using", "get", "gets", "got", "gotten", "set", "sets",
    "put", "puts", "call", "calls", "called", "make", "makes", "made",
    "take", "takes", "took", "taken", "have", "has", "had", "do", "does",
    "did", "done", "go", "goes", "went", "gone", "come", "comes", "came",
    "work", "works", "worked", "try", "tries", "tried", "need", "needs",
    "needed", "want", "wants", "wanted", "like", "likes", "liked", "look",
    "looks", "looked", "see", "sees", "saw", "seen", "know", "knows", "knew",
    "find", "finds", "found", "give", "gives", "gave", "given", "tell",
    "tells", "told", "say", "says", "said", "ask", "asks", "asked", "show",
    "shows", "showed", "shown", "run", "runs", "ran", "move", "moves", "moved",
    "help", "helps", "helped", "start", "starts", "started", "turn", "turns",
    "turned", "play", "plays", "played", "live", "lives", "lived", "believe",
    "believes", "believed", "bring", "brings", "brought", "happen", "happens",
    "happened", "write", "writes", "wrote", "written", "provide", "provides",
    "provided", "sit", "sits", "sat", "stand", "stands", "stood", "lose",
    "loses", "lost", "pay", "pays", "paid", "meet", "meets", "met", "include",
    "includes", "included", "continue", "continues", "continued", "change",
    "changes", "changed", "follow", "follows", "followed", "stop", "stops",
    "stopped", "create", "creates", "created", "speak", "speaks", "spoke",
    "read", "reads", "allow", "allows", "allowed", "add", "adds", "added",
    "spend", "spends", "spent", "grow", "grows", "grew", "grown", "open",
    "opens", "opened", "walk", "walks", "walked", "win", "wins", "won",
    "offer", "offers", "offered", "remember", "remembers", "remembered",
    "love", "loves", "loved", "consider", "considers", "considered",
    "appear", "appears", "appeared", "buy", "buys", "bought", "wait",
    "waits", "waited", "serve", "serves", "served", "die", "dies", "died",
    "send", "sends", "sent", "expect", "expects", "expected", "build",
    "builds", "built", "stay", "stays", "stayed", "fall", "falls", "fell",
    "fallen", "cut", "cuts", "reach", "reaches", "reached", "kill", "kills",
    "killed", "remain", "remains", "remained", "suggest", "suggests",
    "suggested", "raise", "raises", "raised", "pass", "passes", "passed",
    "sell", "sells", "sold", "require", "requires", "required", "report",
    "reports", "reported", "decide", "decides", "decided", "pull", "pulls",
    "pulled", "explain", "explains", "explained", "carry", "carries",
    "carried", "develop", "develops", "developed", "hope", "hopes", "hoped",
    "drive", "drives", "drove", "driven", "break", "breaks", "broke",
    "broken", "receive", "receives", "received", "agree", "agrees", "agreed",
    "support", "supports", "supported", "remove", "removes", "removed",
    "leave", "leaves", "left", "enter", "enters", "entered", "check",
    "checks", "checked", "feel", "feels", "felt", "seem", "seems", "seemed",
}

# Admission thresholds
_MIN_FREQ_TO_PERSIST = 2
_MIN_TERM_CONFIDENCE = 0.15
_DISCOVERY_BOOST = 0.05
_MAX_TERM_CONFIDENCE = 1.0

# Length limits
_ZH_WHOLE_PHRASE_MAX = 6   # Whole Chinese phrases >6 chars are likely sentences
_ZH_NGRAM_MAX = 4
_EN_WORD_MIN = 3
_EN_WORD_MAX = 20
_EN_PROPER_MAX = 30


def _is_generic_verb(word: str) -> bool:
    """Check if word (or a common inflection of it) is a generic verb."""
    if word in _EN_GENERIC_VERBS:
        return True
    # Check common inflections: handles -> handle, handled -> handle, handling -> handle
    for suffix, restore_e in (("s", False), ("es", False), ("ed", False), ("ing", True)):
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if stem in _EN_GENERIC_VERBS:
                return True
            if restore_e and stem + "e" in _EN_GENERIC_VERBS:
                return True
    return False


class TermMeta:
    """Lightweight metadata for a single domain term. No Pydantic — plain object."""

    __slots__ = ("freq", "last_seen", "confidence")

    def __init__(self, freq: int = 0, last_seen: datetime | None = None, confidence: float = 1.0):
        self.freq = freq
        self.last_seen = last_seen or datetime.now(timezone.utc)
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "freq": self.freq,
            "last_seen": self.last_seen.isoformat(),
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TermMeta":
        return cls(
            freq=d.get("freq", 0),
            last_seen=datetime.fromisoformat(d["last_seen"]),
            confidence=d.get("confidence", 1.0),
        )


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
        # In-memory staging: terms seen only once are held here, not persisted.
        # Key: (project_id, token) -> count
        self._staging: dict[tuple[int | None, str], int] = {}

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
        payload = {
            "terms": {k: v.to_dict() for k, v in terms.items()},
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

        # 1. English words (>=3 chars, exclude generic verbs & stopwords)
        for w in _EN_WORD_RE.findall(content):
            w_lower = w.lower()
            if (
                len(w_lower) < _EN_WORD_MIN
                or len(w_lower) > _EN_WORD_MAX
                or w_lower in ALL_STOPWORDS
                or _is_generic_verb(w_lower)
                or _PURE_NUM_RE.match(w_lower)
            ):
                continue
            counts[w_lower] = counts.get(w_lower, 0) + 1

        # 2. Chinese phrases
        for phrase in _ZH_WORD_RE.findall(content):
            # 2a. Whole phrase — keep only if 2-6 chars and not a stopword
            if 2 <= len(phrase) <= _ZH_WHOLE_PHRASE_MAX and phrase not in ALL_STOPWORDS:
                counts[phrase] = counts.get(phrase, 0) + 1

            # 2b. N-grams (2-4 chars)
            if len(phrase) >= 2:
                max_n = min(_ZH_NGRAM_MAX + 1, len(phrase) + 1)
                for n in range(2, max_n):
                    for i in range(len(phrase) - n + 1):
                        sub = phrase[i:i + n]
                        if sub in ALL_STOPWORDS:
                            continue
                        if n == 2:
                            # Bigrams: strict — any stopword inside → reject
                            if any(ch in ALL_STOPWORDS for ch in sub):
                                continue
                        else:
                            # 3+ grams: reject only if BOTH ends are stopwords
                            # (allows terms like "不可抗力" where "不" is a stopword)
                            if sub[0] in ALL_STOPWORDS and sub[-1] in ALL_STOPWORDS:
                                continue
                        counts[sub] = counts.get(sub, 0) + 1

        # 3. English proper noun phrases (API Gateway, Data Model, ...)
        for phrase in _EN_PROPER_RE.findall(content):
            words = phrase.lower().split()
            words = [w for w in words if w not in ALL_STOPWORDS and w not in _EN_GENERIC_VERBS]
            if len(words) >= 2:
                normalized = " ".join(words)
                if len(normalized) <= _EN_PROPER_MAX:
                    counts[normalized] = counts.get(normalized, 0) + 1

        return counts

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
        memory_confidence: float = 0.5,
    ) -> None:
        """
        Extract candidate terms from content and update the term bank.

        Only terms from memories with confidence >= 0.5 are considered reliable
        enough to contribute to the bank.

        Terms are persisted only after they have been seen >= _MIN_FREQ_TO_PERSIST
        times (first sightings are kept in a memory-only staging cache).
        """
        if memory_confidence < 0.5:
            return

        tokens = self._extract_tokens(content)
        if not tokens:
            return

        now = datetime.now(timezone.utc)
        staging_key = project_id

        async with self._lock:
            persisted = await self._load(project_id)
            newly_promoted: list[str] = []

            for token, count in tokens.items():
                if token in persisted:
                    # Already persisted — just boost
                    meta = persisted[token]
                    meta.freq += count
                    meta.last_seen = now
                    meta.confidence = min(
                        meta.confidence + _DISCOVERY_BOOST * memory_confidence,
                        _MAX_TERM_CONFIDENCE,
                    )
                else:
                    # Staging: accumulate in memory until threshold
                    key = (staging_key, token)
                    self._staging[key] = self._staging.get(key, 0) + count
                    if self._staging[key] >= _MIN_FREQ_TO_PERSIST:
                        # Promote to persisted
                        persisted[token] = TermMeta(
                            freq=self._staging[key],
                            last_seen=now,
                            confidence=min(
                                _DISCOVERY_BOOST * memory_confidence + 0.3,
                                _MAX_TERM_CONFIDENCE,
                            ),
                        )
                        newly_promoted.append(token)
                        del self._staging[key]

            if newly_promoted:
                logger.debug(
                    f"[TermBank] Promoted {len(newly_promoted)} terms to persistence "
                    f"for project={project_id}"
                )

            await self._save(project_id, persisted)

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
            (token, meta.confidence * (1 + math.log(meta.freq + 1)))
            for token, meta in terms.items()
            if meta.confidence >= min_confidence
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [token for token, _ in scored[:limit]]
