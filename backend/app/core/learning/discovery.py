import json
import logging
import os
import shutil
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import Field
from sqlalchemy import select

from app.core.config import settings
from app.core.learning.prompts import prompt_builder
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm import get_default_llm
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


class SkillParams(DynamicBaseModel):
    """Dynamic parameters extracted during skill matching."""


class SkillListItem(DynamicBaseModel):
    """Lightweight item for active skills list."""
    id: int
    name: str
    namespace: str = "general"
    description: str = ""


class SkillMatch(DynamicBaseModel):
    """Result of skill matching (intentional execution)."""
    skill_id: int
    skill_name: str
    confidence: float
    reasoning: str
    extracted_params: SkillParams = Field(default_factory=SkillParams)


class SkillDiscovery:
    """
    Unified Service for Skill Matching (Intent) and Skill Retrieval (Knowledge).
    Phase 5: Strictly uses deterministic namespace routing and regex matching.
    Vector semantic recall has been deprecated to prevent skill hallucinations.
    """

    def __init__(self):
        self._skills_cache: list[LearnedSkill] | None = None
        self._id_map: dict[int, LearnedSkill] = {}
        self._name_map: dict[str, LearnedSkill] = {}
        self._skills_list_cache: list[SkillListItem] | None = None
        self._system_skills_synced = False

    async def _sync_system_skills(self):
        """
        Sync system skills to the DB.

        Workflow:
        1. Copy built-in skills from app/config/skills to ~/.evoloop/skills
        2. Scan ~/.evoloop/skills directory and import/update skills in DB
        """
        if self._system_skills_synced:
            return

        try:
            from app.core.learning.skill_importer import SkillImporter

            # Step 1: Copy built-in skills to user skills directory
            # Built-in skills are now located in app/config/skills
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            builtin_skills_path = os.path.join(base_dir, "config", "skills")
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
        from app.utils.path import ensure_dir
        ensure_dir(user_path)

        for root, dirs, files in os.walk(builtin_path):
            # Calculate relative path from builtin skills root
            rel_path = os.path.relpath(root, builtin_path)
            target_dir = os.path.join(user_path, rel_path)

            # Create target directory
            ensure_dir(target_dir)

            # Copy files
            for file in files:
                source_file = os.path.join(root, file)
                target_file = os.path.join(target_dir, file)

                # Copy if target doesn't exist or source is newer
                if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
                    shutil.copy2(source_file, target_file)
                    logger.debug(f"[Discovery] Copied skill file: {rel_path}/{file}")

    async def _get_active_skills(self, force_reload: bool = False) -> list[LearnedSkill]:
        """
        [Phase 5 Optimization] Persistence Cache.
        Fetch active skills with long-term memory residency.
        """
        if not force_reload and self._skills_cache is not None:
            return self._skills_cache

        await self._sync_system_skills()

        async with session_scope() as db:
            stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
            result = await db.execute(stmt)
            items = list(result.scalars().all())

            # Populate Memory Maps for O(1) Lookup
            self._id_map = {s.id: s for s in items}
            self._name_map = {s.name.lower(): s for s in items}

            self._skills_cache = items

            # Clear derivative caches to force re-calculation if needed
            self._skills_list_cache = None

            logger.info(f"[Discovery] Specialized expertise indexed: {len(self._id_map)} skills resident in memory.")

        return self._skills_cache

    async def get_skill_by_id(self, skill_id: int) -> LearnedSkill | None:
        """
        Phase 5 Deterministic Routing:
        Fetch a specific skill by its unique ID.
        Uses O(1) Memory Indexing.
        """
        if not skill_id:
            return None

        await self._get_active_skills()
        return self._id_map.get(skill_id)

    async def _get_skills_by_namespace(self, namespace_prefix: str) -> list[LearnedSkill]:
        """
        Phase 5 Deterministic Routing:
        Fetch skills strictly within a given directory tree (namespace).
        Now utilizes in-memory filtering to reduce DB I/O.
        """
        all_skills = await self._get_active_skills()
        if not namespace_prefix:
            return all_skills

        return [
            s for s in all_skills
            if s.namespace and s.namespace.startswith(namespace_prefix)
        ]

    async def reload(self):
        """
        Force a full refresh of the in-memory skill cache and indices.
        Call this after DB mutations.
        """
        await self._get_active_skills(force_reload=True)

    # --- Phase 5: Deterministic "Yellow Pages" Discovery ---

    async def exact_search(
        self,
        query: str,
        namespace_context: str | None = None,
        **kwargs
    ) -> tuple[SkillMatch | None, list[LearnedSkill], str]:
        """
        Deterministic Skill lookup based on ID or Exact Name.
        Uses O(1) Memory Indexing.
        """
        # Ensure cache is ready (will be warm at startup, but safe fallback)
        all_skills = await self._get_active_skills()

        if not query:
            return None, [], "Empty query provided."

        query_clean = str(query).strip()

        # 1. Try ID lookup (O(1))
        best_skill = None
        if query_clean.isdigit():
            target_id = int(query_clean)
            best_skill = self._id_map.get(target_id)

        # 2. Try Exact Name lookup (O(1))
        if not best_skill:
            query_lower = query_clean.lower()
            best_skill = self._name_map.get(query_lower)

        # 3. Try Namespace-Prefix lookup (O(N) Fallback for specific tree traversal)
        if not best_skill and "/" in query_clean:
            # Simple prefix match within the same depth
            best_skill = next((s for s in all_skills if s.name.startswith(query_clean)), None)

        if best_skill:
            match = SkillMatch(
                skill_id=best_skill.id,
                skill_name=best_skill.name,
                confidence=1.0,
                reasoning="Deterministic match found.",
                extracted_params={}
            )
            return match, [best_skill], "Exact match found."

        # If no deterministic match, return empty.
        # We no longer trigger implicit LLM here to ensure transparency.
        logger.info(f"[Discovery] No deterministic match for: {query_clean}")
        return None, [], "No exact match found."

    async def match_multiple(
        self,
        query: str,
        task_steps: list[str] | None = None,
        namespace_context: str | None = None,
        max_skills: int = 3
    ) -> tuple[list[SkillMatch], str]:
        """
        Match multiple skills for complex multi-step tasks.
        
        Args:
            query: The main task description
            task_steps: Optional list of identified steps (e.g., ["search web", "send to wechat"])
            namespace_context: Optional namespace filter
            max_skills: Maximum number of skills to return
            
        Returns:
            Tuple of (list of SkillMatch, reasoning)
        """
        all_skills = await self._get_active_skills()
        matches = []

        # If explicit steps provided, match each step
        if task_steps and len(task_steps) > 1:
            logger.info(f"[Discovery] Multi-step task detected: {len(task_steps)} steps")

            for step in task_steps:
                # Try exact match first
                match, _, _ = await self.exact_search(step, namespace_context)

                if not match:
                    # Fallback to semantic search for this step
                    match, _, _ = await self.semantic_search(step, namespace_context=namespace_context)

                if match and match.skill_id not in [m.skill_id for m in matches]:
                    matches.append(match)

                if len(matches) >= max_skills:
                    break

        # If no matches from steps, try to extract multiple intents from main query
        if not matches:
            # Use LLM to analyze if this is a multi-skill task
            analysis = await self._analyze_task_complexity(query)

            if analysis.get("is_multi_step", False):
                for skill_name in analysis.get("required_skills", [])[:max_skills]:
                    match, _, _ = await self.exact_search(skill_name, namespace_context)
                    if match and match.skill_id not in [m.skill_id for m in matches]:
                        matches.append(match)

        reasoning = f"Matched {len(matches)} skills for multi-step task"
        return matches, reasoning

    async def _analyze_task_complexity(self, query: str) -> dict:
        """
        Analyze if a task requires multiple skills.
        Uses lightweight LLM call with modular prompt template.
        """
        from app.core.learning.prompts import prompt_builder

        # Use modular prompt template instead of hardcoded string
        prompt = prompt_builder.build_task_complexity_prompt(query)

        # Fallback to basic structure if template rendering failed
        if prompt.startswith("Error loading"):
            logger.warning("[Discovery] Failed to load task complexity template, using fallback")
            return {"is_multi_step": False, "required_skills": [], "reasoning": "Template load failed"}

        try:
            from app.core.llm import InternalLLMService
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": prompt}],
                purpose="task_analysis",
                temperature=0.0,
            )

            content = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            if "```json" in content:
                content = content.split("```json")[-1].split("```")[0].strip()

            return json.loads(content)
        except Exception as e:
            logger.error(f"[Discovery] Task analysis failed: {e}")
            return {"is_multi_step": False, "required_skills": [], "reasoning": "Analysis failed"}

    async def semantic_search(
        self,
        query: str,
        history: list[dict] | None = None,
        namespace_context: str | None = None,
        current_plan: str | None = None,
        user_preferences: Any | None = None
    ) -> tuple[SkillMatch | None, list[LearnedSkill], str]:
        """
        Pure LLM-Based Skill Discovery with History support.
        Intent Caching has been DISABLED to prioritize accuracy.
        Used by explicit search tools.
        """
        # Ensure cache is ready
        all_skills = await self._get_active_skills()
        if not all_skills:
            return None, [], "No active skills available to match."

        # 2. Build LLM Context
        prompt_vars = {
            "catalog": "\n".join([
                f"- ID: {s.id} | Name: {s.name} | Description: {s.description}"
                for s in all_skills
            ]),
            "current_plan": current_plan or "None",
            "user_preferences": user_preferences or "None"
        }

        system_prompt = prompt_builder.build_discovery_prompt(prompt_vars)

        try:
            from app.core.context.manager import ContextManager
            model = ContextManager.current().active_model
            llm = await get_default_llm(temperature=0.0, model=model)
            messages = [
                SystemMessage(content=system_prompt)
            ]

            # Incorporate history if provided
            if history:
                for msg in history[-5:]:  # Last 5 turns for context
                    role = msg.get("role", "human")
                    content = msg.get("content", "")
                    if role == "human":
                        messages.append(HumanMessage(content=content))
                    elif role == "ai":
                        messages.append(AIMessage(content=content))

            messages.append(HumanMessage(content=query))

            logger.info(f"[Discovery] Invoking LLM for intent matching: {query[:50]}...")
            response = await llm.ainvoke(
                messages,
                config={"callbacks": []}
            )

            # Simple brain-style JSON parser
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[-1].split("```")[0].strip()

            try:
                data = json.loads(content)
            except Exception as e:
                logger.error(f"[Discovery] JSON Parse Error: {e}. Content: {content}")
                return None, [], f"JSON Parse Error: {e}"

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
                    logger.info(f"[Discovery] Semantic Match Found: {best_skill.name} (Conf: {match.confidence})")

            if not match:
                logger.info(f"[Discovery] Semantic search decided NO_MATCH for: {query[:50]}. Reasoning: {reasoning}")
                relevant = (all_skills if namespace_context else [])

            return match, relevant, reasoning

        except Exception as e:
            logger.error(f"[Discovery] Semantic matching failed: {e}")
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

    async def get_active_skills_list(self) -> list[SkillListItem]:
        """
        Returns a flat list of all active skills as dictionaries.
        Uses in-memory cache to avoid redundant conversions.
        """
        if self._skills_list_cache is not None:
            return self._skills_list_cache

        all_skills = await self._get_active_skills()
        self._skills_list_cache = [
            SkillListItem(
                id=s.id,
                name=s.name,
                namespace=s.namespace or "general",
                description=(s.description or "No description.").replace('\n', ' ')
            )
            for s in all_skills
        ]
        return self._skills_list_cache

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
        match, _, _ = await self.exact_search(user_input)
        if match and match.confidence >= threshold:
            return match
        return None

    async def retrieve(self, topic: str, history: list[dict] | None = None, top_k: int = 3) -> list[LearnedSkill]:
        """Backward compatible wrapper for knowledge retrieval."""
        _, relevant, _ = await self.exact_search(topic)
        return relevant

# Singleton
skill_discovery = SkillDiscovery()
