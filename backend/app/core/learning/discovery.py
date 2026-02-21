import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select, text

from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """Result of skill matching (intentional execution)."""
    skill_id: int
    skill_name: str
    confidence: float
    extracted_params: dict[str, Any]


class SkillDiscovery:
    """
    Unified Service for Skill Matching (Intent) and Skill Retrieval (Knowledge).
    Phase 5: Strictly uses deterministic namespace routing and regex matching.
    Vector semantic recall has been deprecated to prevent skill hallucinations.
    """

    def __init__(self):
        self._skills_cache: list[LearnedSkill] | None = None
        self._cache_expiry = 0
        self._system_skills_synced = False

    async def _sync_system_skills(self):
        """Sync system SOPs from the local library to the DB."""
        if self._system_skills_synced:
            return
        
        try:
            from app.core.learning.skill_importer import SkillImporter
            import os
            
            # Resolve the absolute path to the sop_library
            # current file is app/core/learning/discovery.py
            base_dir = os.path.dirname(os.path.abspath(__file__))
            sop_library_path = os.path.join(base_dir, "sop_library")
            
            if os.path.exists(sop_library_path):
                logger.info(f"[Discovery] Pre-seeding system SOPs from {sop_library_path}")
                await SkillImporter.import_from_directory(sop_library_path)
            
            self._system_skills_synced = True
        except Exception as e:
            logger.error(f"[Discovery] Failed to sync system SOPs: {e}")

    async def _get_active_skills(self) -> list[LearnedSkill]:
        """Cache-active skills from DB."""
        await self._sync_system_skills()
        
        now = time.time()
        if self._skills_cache and now < self._cache_expiry:
            return self._skills_cache
        
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
            result = await db.execute(stmt)
            self._skills_cache = list(result.scalars().all())
            self._cache_expiry = now + 60
        return self._skills_cache

    async def _get_skills_by_namespace(self, namespace_prefix: str) -> list[LearnedSkill]:
        """
        Phase 5 Deterministic Routing:
        Fetch skills strictly within a given directory tree (namespace).
        e.g., namespace_prefix='os/macos' will match 'os/macos/click' and 'os/macos/copy'
        """
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(
                LearnedSkill.is_active == True,
                LearnedSkill.namespace.like(f"{namespace_prefix}%")
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

    # --- Tier 1: Regex Matching ---

    def _pattern_to_regex(self, pattern: str) -> str:
        escaped = re.escape(pattern)
        regex = re.sub(r"\\{(\w+)\\}", r"(?P<\1>.+?)", escaped)
        return f"^{regex}$"

    async def _match_regex(self, text_input: str) -> Optional[SkillMatch]:
        skills = await self._get_active_skills()
        for skill in skills:
            if not skill.trigger_patterns:
                continue
            try:
                patterns = json.loads(skill.trigger_patterns) if isinstance(skill.trigger_patterns, str) else skill.trigger_patterns
                for p in patterns:
                    regex = self._pattern_to_regex(p)
                    match = re.match(regex, text_input, re.IGNORECASE)
                    if match:
                        return SkillMatch(
                            skill_id=skill.id,
                            skill_name=skill.name,
                            confidence=1.0, # Regex is 100% confident
                            extracted_params=match.groupdict()
                        )
            except Exception:
                continue
        return None

    # --- Phase 5: Deterministic "Yellow Pages" Discovery ---

    async def exact_search(
        self, 
        query: str, 
        namespace_context: str | None = None
    ) -> tuple[Optional[SkillMatch], list[LearnedSkill]]:
        """
        Deterministic Lookup (Phase 5).
        1. Exact Regex Hit -> Returns Match (to run immediately)
        2. Namespace Match -> Returns all SOP instructions under that tree to the LLM (In-Context)
        3. Fails soft -> Returns empty list, forcing the LLM to write manual bash code.
        """
        # 1. Tier 1: Exact Regex Match (User explicitly commands a known pattern)
        match = await self._match_regex(query)
        if match:
            async with session_scope() as db:
                skill = await db.get(LearnedSkill, match.skill_id)
                return match, [skill] if skill else []

        # 2. Tier 2: Namespace Mount (System automatically mounts SOPs for current context)
        # E.g. If the EvolutionContext bus detects we are in Xcode, query might be implicitly scoped 
        # to `domain/xcode`
        relevant = []
        if namespace_context:
            logger.info(f"[Discovery] Mounting skill tree for namespace: {namespace_context}")
            relevant = await self._get_skills_by_namespace(namespace_context)
            
        return None, relevant

    async def discover(
        self, 
        user_input: str, 
        thread_id: str = None,
        top_k: int = 3
    ) -> tuple[Optional[SkillMatch], list[LearnedSkill]]:
        """
        Internal dispatcher. Uses exact search by default.
        """
        return await self.exact_search(user_input)

    async def match(self, user_input: str, threshold: float = 0.5, thread_id: str = None) -> Optional[SkillMatch]:
        """Backward compatible wrapper for intent matching."""
        match, _ = await self.exact_search(user_input)
        if match and match.confidence >= threshold:
            return match
        return None

    async def retrieve(self, topic: str, top_k: int = 3) -> list[LearnedSkill]:
        """Backward compatible wrapper for knowledge retrieval."""
        _, relevant = await self.exact_search(topic)
        return relevant

    # [Deprecated Compatibility]
    async def get_relevant_skills(self, topic: str, top_k: int = 3, **kwargs) -> list[LearnedSkill]:
        """Alias for retrieve to support drop-in replacement for SkillRetriever."""
        return await self.retrieve(topic, top_k=top_k)


# Singleton
skill_discovery = SkillDiscovery()
