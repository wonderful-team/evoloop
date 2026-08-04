import logging
import os
import shutil
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.learning.schemas import SkillListItem, SkillMatch
from app.core.learning.skill_importer import SkillImporter
from app.core.learning.skill_visibility import visible_filter
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


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

    async def ensure_system_skills_synced(self):
        """
        One-time bootstrap of built-in skills into the DB (public, idempotent).

        Workflow:
        1. Copy built-in skills from app/config/skills to ~/.evoloop/skills
        2. Scan ~/.evoloop/skills directory and import/update skills in DB

        No-op after the first successful sync (in-memory flag + the
        SYSTEM_SKILLS_SYNCED config value), so read paths may call it freely.
        """
        if self._system_skills_synced:
            return

        try:
            # Check DB flag to ensure this is only run on first startup
            if SystemConfigService.get_value("SYSTEM_SKILLS_SYNCED") == "true":
                self._system_skills_synced = True
                return

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

            # Save status flag in database
            SystemConfigService.set_value(
                "SYSTEM_SKILLS_SYNCED",
                "true",
                "Indicates that the system skills have been successfully synchronized on first launch",
            )
            self._system_skills_synced = True
        except Exception as e:
            logger.error(f"[Discovery] Failed to sync system SOPs: {e}")

    def _copy_builtin_skills(self, builtin_path: str, user_path: str) -> None:
        """
        Copy built-in skills to user skills directory.
        Only copies new or updated skills (based on modification time).
        """
        from app.core.file import ensure_dir

        ensure_dir(user_path)

        from app.core.file import FileTraverser, TraverseOptions

        options = TraverseOptions(include_dirs=False)

        for source_file in FileTraverser.walk(builtin_path, options):
            # Calculate relative path from builtin skills root
            rel_file_path = os.path.relpath(source_file, builtin_path)
            target_file = os.path.join(user_path, rel_file_path)

            # Ensure target directory exists
            os.makedirs(os.path.dirname(target_file), exist_ok=True)

            # Copy if target doesn't exist or source is newer
            if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
                shutil.copy2(source_file, target_file)
                logger.debug(f"[Discovery] Copied skill file: {rel_file_path}")

    async def _get_active_skills(self, force_reload: bool = False) -> list[LearnedSkill]:
        """
        [Phase 5 Optimization] Persistence Cache.
        Fetch active skills with long-term memory residency.
        """
        if not force_reload and self._skills_cache is not None:
            return self._skills_cache

        await self.ensure_system_skills_synced()

        async with session_scope() as db:
            stmt = select(LearnedSkill).where(visible_filter())
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
                extracted_params={},
            )
            return match, [best_skill], "Exact match found."

        # If no deterministic match, return empty.
        # We no longer trigger implicit LLM here to ensure transparency.
        logger.info(f"[Discovery] No deterministic match for: {query_clean}")
        return None, [], "No exact match found."

    async def get_skills_catalog(
        self,
        namespace: str | None = None,
        query: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Fast O(1) retrieval of the skills catalog.
        Optionally filter by namespace and a simple case-insensitive substring query.
        """
        all_skills = await self._get_active_skills()

        results = []
        for s in all_skills:
            if namespace and s.namespace != namespace:
                continue

            if query:
                q = query.lower()
                name_match = s.name and q in s.name.lower()
                desc_match = s.description and q in s.description.lower()
                if not (name_match or desc_match):
                    continue

            results.append({
                "id": s.id,
                "name": s.name,
                "namespace": s.namespace or "general",
                "description": s.description or ""
            })
            
        return results

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
                description=(s.description or "No description.").replace("\n", " "),
            )
            for s in all_skills
        ]
        return self._skills_list_cache


# Singleton
skill_discovery = SkillDiscovery()
