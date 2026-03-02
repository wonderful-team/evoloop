import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.config import settings
from app.infrastructure.database.redis import redis_client
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.factory import LLMFactory
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """Result of skill matching (intentional execution)."""
    skill_id: int
    skill_name: str
    confidence: float
    reasoning: str
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
        """
        Sync system skills to the DB.

        Workflow:
        1. Copy built-in skills from app/core/learning/skills to ~/.evoloop/skills
        2. Scan ~/.evoloop/skills directory and import/update skills in DB
        """
        if self._system_skills_synced:
            return

        try:
            from app.core.learning.skill_importer import SkillImporter

            # Step 1: Copy built-in skills to user skills directory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            builtin_skills_path = os.path.join(base_dir, "skills")
            user_skills_path = settings.SKILLS_DIR

            if os.path.exists(builtin_skills_path):
                logger.info(f"[Discovery] Syncing built-in skills to {user_skills_path}")
                self._copy_builtin_skills(builtin_skills_path, user_skills_path)

            # Step 2: Import skills from user skills directory
            if os.path.exists(user_skills_path):
                logger.info(f"[Discovery] Loading skills from {user_skills_path}")
                await SkillImporter.import_from_directory(user_skills_path)

            self._system_skills_synced = True
        except Exception as e:
            logger.error(f"[Discovery] Failed to sync system SOPs: {e}")

    def _copy_builtin_skills(self, builtin_path: str, user_path: str) -> None:
        """
        Copy built-in skills to user skills directory.
        Only copies new or updated skills (based on modification time).
        """
        if not os.path.exists(user_path):
            os.makedirs(user_path, exist_ok=True)

        for root, dirs, files in os.walk(builtin_path):
            # Calculate relative path from builtin skills root
            rel_path = os.path.relpath(root, builtin_path)
            target_dir = os.path.join(user_path, rel_path)

            # Create target directory
            os.makedirs(target_dir, exist_ok=True)

            # Copy files
            for file in files:
                source_file = os.path.join(root, file)
                target_file = os.path.join(target_dir, file)

                # Copy if target doesn't exist or source is newer
                if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
                    shutil.copy2(source_file, target_file)
                    logger.debug(f"[Discovery] Copied skill file: {rel_path}/{file}")

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

    # --- Phase 5: Deterministic "Yellow Pages" Discovery ---

    async def exact_search(
        self,
        query: str,
        history: list[dict] | None = None,
        namespace_context: str | None = None
    ) -> tuple[SkillMatch | None, list[LearnedSkill], str]:
        """
        Pure LLM-Based Skill Discovery with History support and Redis Caching.
        """
        # 0. Check Cache (Phase 5 Optimization)
        history_str = json.dumps(history[-3:] if history else [])
        cache_key = f"evo:intent_cache:{hashlib.md5((query + history_str).encode()).hexdigest()}"
        
        try:
            cached_res = await redis_client.get(cache_key)
            if cached_res:
                data = json.loads(cached_res)
                logger.info(f"[Discovery] Intent Cache Hit for: {query[:30]}...")
                
                match = None
                if data.get("match"):
                    m = data["match"]
                    match = SkillMatch(
                        skill_id=m["skill_id"],
                        skill_name=m["skill_name"],
                        confidence=m["confidence"],
                        reasoning=m["reasoning"] + " (Cached)",
                        extracted_params=m["extracted_params"]
                    )
                
                # Note: For simplicity in cache, we don't full-hydrate the 'relevant' list if missed, 
                # but SkillMatch presence is the primary driver.
                relevant = []
                if match:
                    async with session_scope() as db:
                        s = await db.get(LearnedSkill, match.skill_id)
                        if s: relevant = [s]
                
                return match, relevant, data.get("reasoning", "")
        except Exception as e:
            logger.warning(f"[Discovery] Cache lookup failed: {e}")

        # Ensure system SOPs are loaded into the DB
        await self._sync_system_skills()

        # 1. Prepare candidate pool
        all_skills = await self._get_active_skills()
        if not all_skills:
            return None, []

        # 2. Build LLM Context
        skill_catalog = "\n".join([
            f"- ID: {s.id} | Name: {s.name} | Description: {s.description}"
            for s in all_skills
        ])

        system_prompt = """You are the EvoLoop Skill Router. 
Match the USER_QUERY to the most relevant skill in the CATALOG.

CATALOG:
{catalog}

RULES:
1. If the CURRENT_USER_QUERY contains a task request (even if preceded by "nevermind" or "cancel previous"), match it to the best skill.
2. If the query is ONLY a conversational filler or confirmation (e.g. "Agreed", "Okay", "Done"), return NO_MATCH.
3. Handle cross-lingual mapping (ZH query -> EN skill).
4. If the user switched from one task to another in the same message, prioritize the NEW task.
5. In multi-turn context (PREVIOUS_QUERY/RESPONSE), identify if the user is confirmation a previous suggestion OR starting something new.

OUTPUT FORMAT (JSON ONLY):
{{
  "match_found": bool,
  "skill_id": int or null,
  "skill_name": "string or null",
  "confidence": float (0.0 to 1.0),
  "reasoning": "brief explanation",
  "parameters": {{ "key": "value" }}
}}"""

        try:
            llm = LLMFactory.create_llm(temperature=0.0)  # High precision
            messages = [
                SystemMessage(content=system_prompt.format(catalog=skill_catalog))
            ]

            # Incorporate history if provided
            if history:
                for msg in history[-5:]:  # Last 5 turns for context
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        messages.append(HumanMessage(content=f"PREVIOUS_QUERY: {content}"))
                    elif role == "assistant":
                        messages.append(AIMessage(content=f"PREVIOUS_RESPONSE: {content}"))

            messages.append(HumanMessage(content=f"CURRENT_USER_QUERY: {query}"))

            logger.info(f"[Discovery] Invoking LLM for intent matching: {query[:50]}...")
            response = await llm.ainvoke(messages)

            # Simple brain-style JSON parser
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[-1].split("```")[0].strip()

            try:
                data = json.loads(content)
            except Exception as e:
                logger.error(f"[Discovery] JSON Parse Error: {e}. Content: {content}")
                return None, []

            match = None
            relevant = []
            reasoning = data.get("reasoning", "")

            if data.get("match_found"):
                # Double check ID exists in our list
                found_id = data.get("skill_id")
                best_skill = next((s for s in all_skills if s.id == found_id), None)

                if best_skill:
                    match = SkillMatch(
                        skill_id=best_skill.id,
                        skill_name=best_skill.name,
                        confidence=data.get("confidence", 0.8),
                        reasoning=reasoning,
                        extracted_params=data.get("parameters", {})
                    )
                    relevant = [best_skill]
                    logger.info(f"[Discovery] LLM Match Found: {best_skill.name} (Conf: {match.confidence})")

            # 3. Store in Cache (5 minutes)
            try:
                cache_data = {
                    "match": {
                        "skill_id": match.skill_id,
                        "skill_name": match.skill_name,
                        "confidence": match.confidence,
                        "reasoning": match.reasoning,
                        "extracted_params": match.extracted_params
                    } if match else None,
                    "reasoning": reasoning
                }
                await redis_client.set(cache_key, json.dumps(cache_data), ex=300)
            except Exception as e:
                logger.warning(f"[Discovery] Cache write failed: {e}")

            if not match:
                logger.info(f"[Discovery] LLM decided NO_MATCH for: {query[:50]}. Reasoning: {reasoning}")
                relevant = (all_skills if namespace_context else [])

            return match, relevant, reasoning

        except Exception as e:
            logger.error(f"[Discovery] LLM matching failed: {e}")
            return None, [], str(e)

    async def get_namespace_index(self, namespace_context: str) -> list[dict[str, str]]:
        """
        Track 8.1: Eager Namespace Indexing
        Returns a lightweight list of (name, description) for all skills in a namespace.
        Useful for prompt injection without bloating context window.
        """
        if not namespace_context:
            return []

        skills = await self._get_skills_by_namespace(namespace_context)
        return [{"id": s.id, "name": s.name, "description": s.description or ""} for s in skills]

    async def discover(
        self,
        user_input: str,
        history: list[dict] | None = None,
        thread_id: str = None,
        top_k: int = 3
    ) -> tuple[SkillMatch | None, list[LearnedSkill], str]:
        """
        Internal dispatcher. Uses exact search by default.
        """
        return await self.exact_search(user_input, history=history)

    async def match(self, user_input: str, history: list[dict] | None = None, threshold: float = 0.5, thread_id: str = None) -> SkillMatch | None:
        """Backward compatible wrapper for intent matching."""
        match, _, _ = await self.exact_search(user_input, history=history)
        if match and match.confidence >= threshold:
            return match
        return None

    async def retrieve(self, topic: str, history: list[dict] | None = None, top_k: int = 3) -> list[LearnedSkill]:
        """Backward compatible wrapper for knowledge retrieval."""
        _, relevant, _ = await self.exact_search(topic, history=history)
        return relevant

    # [Deprecated Compatibility]
    async def get_relevant_skills(self, topic: str, top_k: int = 3, **kwargs) -> list[LearnedSkill]:
        """Alias for retrieve to support drop-in replacement for SkillRetriever."""
        return await self.retrieve(topic, top_k=top_k)


# Singleton
skill_discovery = SkillDiscovery()
