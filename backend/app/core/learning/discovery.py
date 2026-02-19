import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select, text
from langchain_core.messages import SystemMessage, HumanMessage

from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory

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
    Implements a 3-tier funnel:
    1. Deterministic (Regex)
    2. Vector Recall (pgvector)
    3. Semantic Re-ranking (LLM)
    """

    def __init__(self):
        self._embedder = None
        self._skills_cache: list[LearnedSkill] | None = None
        self._cache_expiry = 0

    @property
    def embedder(self):
        """Lazy-load embedder."""
        if self._embedder is None:
            try:
                self._embedder = EmbedderFactory.get_embedder()
            except Exception as e:
                logger.warning(f"[Discovery] Failed to initialize embedder: {e}")
        return self._embedder

    async def _get_active_skills(self) -> list[LearnedSkill]:
        """Cache-active skills from DB."""
        now = time.time()
        if self._skills_cache and now < self._cache_expiry:
            return self._skills_cache
        
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
            result = await db.execute(stmt)
            self._skills_cache = list(result.scalars().all())
            self._cache_expiry = now + 60
        return self._skills_cache

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

    # --- Tier 2: Vector Search ---

    async def _vector_recall(self, topic: str, top_k: int = 10) -> list[LearnedSkill]:
        if not self.embedder:
            return []
        
        try:
            query_embedding = await self.embedder.embed_query(topic)
            if not query_embedding:
                return []
            
            emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            async with session_scope() as db:
                sql = text(f"""
                    SELECT id FROM learned_skills
                    WHERE is_active = true AND embedding IS NOT NULL
                    ORDER BY embedding <=> '{emb_str}'::vector
                    LIMIT :top_k
                """)
                result = await db.execute(sql, {"top_k": top_k})
                ids = [row.id for row in result.fetchall()]
                
                skills = []
                for sid in ids:
                    s = await db.get(LearnedSkill, sid)
                    if s: skills.append(s)
                return skills
        except Exception as e:
            logger.warning(f"[Discovery] Vector recall failed: {e}")
            return []

    # --- Tier 3: LLM Re-ranking ---

    async def _llm_rerank(
        self, 
        user_input: str, 
        candidates: list[LearnedSkill], 
        thread_id: str = None
    ) -> tuple[Optional[SkillMatch], list[LearnedSkill]]:
        """
        Use LLM to decide: 
        1. Is there a primary intent match? 
        2. Which skills are relevant as knowledge?
        """
        if not candidates:
            return None, []

        skill_context = []
        for s in candidates:
            skill_context.append({
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "triggers": s.trigger_patterns
            })

        prompt = f"""Analyze the user's intent and find relevant expert skills (SOPs).

User Request: "{user_input}"

Candidate Skills:
{json.dumps(skill_context, indent=2, ensure_ascii=False)}

Output JSON:
{{
  "intent_match": {{ "skill_id": <id>, "confidence": <0-1>, "params": {{}} }} or null,
  "relevant_skill_ids": [<id1>, <id2>]
}}

Rules:
1. "intent_match" should be non-null ONLY if the user explicitly wants to RUN this specific skill.
2. "relevant_skill_ids" should include top 3 skills that provide helpful background knowledge for this task.
3. If unsure about intent, set intent_match to null but provide relevant_skill_ids.
"""

        try:
            llm = LLMFactory.create_llm(temperature=0)
            resp = await llm.ainvoke([
                SystemMessage(content="You are a skill discovery expert."),
                HumanMessage(content=prompt)
            ], config={"callbacks": []})
            
            # Simple JSON extraction
            content = resp.content.strip()
            if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content: content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            # 1. Resolve Match
            match = None
            im = data.get("intent_match")
            if im and im.get("skill_id"):
                # Hydrate match
                cid = im["skill_id"]
                target = next((s for s in candidates if s.id == cid), None)
                if target:
                    match = SkillMatch(
                        skill_id=target.id,
                        skill_name=target.name,
                        confidence=im.get("confidence", 0.7),
                        extracted_params=im.get("params", {})
                    )

            # 2. Resolve Relevant Skills
            relevant = []
            rel_ids = data.get("relevant_skill_ids", [])
            for rid in rel_ids:
                s = next((s for s in candidates if s.id == rid), None)
                if s: relevant.append(s)

            return match, relevant

        except Exception as e:
            logger.error(f"[Discovery] LLM Reranking failed: {e}")
            return None, candidates[:3] # Fallback to top-3 from vector search

    # --- Unified APIs ---

    async def discover(
        self, 
        user_input: str, 
        thread_id: str = None,
        top_k: int = 3
    ) -> tuple[Optional[SkillMatch], list[LearnedSkill]]:
        """
        The main entry point. Performs Tier 1 -> Tier 2 -> Tier 3.
        Returns: (PrimaryIntentMatch, ListOfRelevantKnowledge)
        """
        # 1. Tier 1: Regex
        match = await self._match_regex(user_input)
        if match:
            # If regex hits, we still might want knowledge for the worker
            # but usually for a direct match, the skill itself is the knowledge.
            # We can skip vector/llm for efficiency if confidence is 1.0
            async with session_scope() as db:
                skill = await db.get(LearnedSkill, match.skill_id)
                return match, [skill] if skill else []

        # 2. Tier 2: Vector Recall
        candidates = await self._vector_recall(user_input, top_k=10)
        
        # 3. Tier 3: LLM Re-ranking (The "Effectiveness" Layer)
        match, relevant = await self._llm_rerank(user_input, candidates, thread_id)
        
        # Log to activity monitor if needed
        if thread_id and (match or relevant):
            try:
                await activity_monitor.update_agent_state(
                    thread_id=thread_id,
                    mode="DISCOVERY",
                    task_name=i18n.get("prompts.skill_executor.task_matching"),
                    task_status=f"Discovered {len(relevant)} relevant skills",
                    details={
                        "type": "thought",
                        "match": match.skill_name if match else None,
                        "relevant": [s.name for s in relevant]
                    }
                )
            except Exception: pass

        return match, relevant[:top_k]

    async def match(self, user_input: str, threshold: float = 0.5, thread_id: str = None) -> Optional[SkillMatch]:
        """Backward compatible wrapper for intent matching."""
        match, _ = await self.discover(user_input, thread_id=thread_id)
        if match and match.confidence >= threshold:
            return match
        return None

    async def retrieve(self, topic: str, top_k: int = 3) -> list[LearnedSkill]:
        """Backward compatible wrapper for knowledge retrieval."""
        _, relevant = await self.discover(topic, top_k=top_k)
        return relevant

    # [Deprecated Compatibility]
    async def get_relevant_skills(self, topic: str, top_k: int = 3, **kwargs) -> list[LearnedSkill]:
        """Alias for retrieve to support drop-in replacement for SkillRetriever."""
        return await self.retrieve(topic, top_k=top_k)

    # --- Maintenance APIs ---

    async def ensure_skill_embeddings(self, batch_size: int = 50) -> int:
        """Generate embeddings for skills that don't have them yet."""
        if not self.embedder:
            logger.warning("[Discovery] Embedder not available, skipping.")
            return 0
        
        updated_count = 0
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(
                LearnedSkill.is_active == True,
                LearnedSkill.embedding == None
            ).limit(batch_size)
            
            result = await db.execute(stmt)
            skills_without_embedding = result.scalars().all()
            
            for skill in skills_without_embedding:
                try:
                    text_v = self._build_embedding_text(skill)
                    emb = await self.embedder.embed_query(text_v)
                    if emb:
                        skill.embedding = emb
                        updated_count += 1
                except Exception as e:
                    logger.warning(f"[Discovery] Failed to embed skill {skill.name}: {e}")
            
            if updated_count > 0:
                await db.commit()
                logger.info(f"[Discovery] Generated embeddings for {updated_count} skills")
        return updated_count

    def _build_embedding_text(self, skill: LearnedSkill) -> str:
        parts = [skill.name]
        if skill.description: parts.append(skill.description)
        if skill.trigger_patterns:
            try:
                triggers = json.loads(skill.trigger_patterns) if isinstance(skill.trigger_patterns, str) else skill.trigger_patterns
                parts.extend(triggers)
            except Exception: parts.append(str(skill.trigger_patterns))
        return " | ".join(parts)


# Singleton
skill_discovery = SkillDiscovery()
