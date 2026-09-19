import logging
import os
import shutil
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.learning.schemas import SkillListItem, SkillMatch
from app.core.learning.skills.importer import SkillImporter
from app.core.learning.skills.visibility import visible_filter
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
            base_dir = os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
            builtin_skills_path = os.path.join(base_dir, "config", "skills")
            user_skills_path = settings.SKILLS_DIR

            if os.path.exists(builtin_skills_path):
                logger.info(
                    f"[Discovery] Syncing built-in skills to {user_skills_path}"
                )
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
            logger.exception(f"[Discovery] Failed to sync system SOPs: {e}")

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
            if not os.path.exists(target_file) or os.path.getmtime(
                source_file
            ) > os.path.getmtime(target_file):
                shutil.copy2(source_file, target_file)
                logger.debug(f"[Discovery] Copied skill file: {rel_file_path}")

    async def _get_active_skills(
        self, force_reload: bool = False
    ) -> list[LearnedSkill]:
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

            logger.info(
                f"[Discovery] Specialized expertise indexed: {len(self._id_map)} skills resident in memory."
            )

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

    async def get_packages_for_domain(self, domain: str | None) -> list[LearnedSkill]:
        """域 → 能力包目录（capability-packages-refactor.md v3）。

        包自声明归属域（capability.domain），DB 查询取代 profile 的 packages
        字段（v3 收敛：作用域模型统一，包是全局资源）。O(内存索引)。
        """
        if not domain:
            return []
        skills = await self._get_active_skills()
        return [
            s
            for s in skills
            if (cap := getattr(s, "capability", None))
            and cap.get("domain") == domain
        ]

    async def get_capability_domains(self) -> list[str]:
        """全部能力包声明的去重域列表（内存缓存遍历，无额外 IO）。

        供跨项目别名桥使用：候选标签（分类器/值守 L1 输出）不是任何包的
        domain 时，按域分组找包归属项目并尝试别名匹配其 profile。
        """
        skills = await self._get_active_skills()
        domains: list[str] = []
        seen: set[str] = set()
        for s in skills:
            cap = getattr(s, "capability", None)
            d = cap.get("domain") if isinstance(cap, dict) else None
            if d and d not in seen:
                seen.add(d)
                domains.append(d)
        return domains

    async def get_capability(self, name: str) -> dict | None:
        """能力包声明（capability-packages-refactor.md §6-#5）。

        O(1) 内存索引（_name_map），非包技能返回 None。ToolManager 过滤层
        每轮调用——依赖既有缓存，不做额外 IO。
        """
        if not name:
            return None
        await self._get_active_skills()
        skill = self._name_map.get(name.strip().lower())
        if skill is None:
            return None
        return getattr(skill, "capability", None)

    async def _get_skills_by_namespace(
        self, namespace_prefix: str
    ) -> list[LearnedSkill]:
        """
        Phase 5 Deterministic Routing:
        Fetch skills strictly within a given directory tree (namespace).
        Now utilizes in-memory filtering to reduce DB I/O.
        """
        all_skills = await self._get_active_skills()
        if not namespace_prefix:
            return all_skills

        return [
            s
            for s in all_skills
            if s.namespace and s.namespace.startswith(namespace_prefix)
        ]

    async def reload(self):
        """
        Force a full refresh of the in-memory skill cache and indices.
        Call this after DB mutations.
        """
        await self._get_active_skills(force_reload=True)
        # 优化：同步失效静态层缓存（技能是全局资源，导入/更新/删除后
        # 各 thread 的 <available_skills> 索引应立即可见，不必等 TTL）。
        try:
            from app.core.context.cache import LayeredContextCache

            LayeredContextCache.invalidate_static(session_id=None)
        except Exception:
            pass

    # --- Phase 5: Deterministic "Yellow Pages" Discovery ---

    async def exact_search(
        self, query: str, namespace_context: str | None = None, **kwargs
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
            best_skill = next(
                (s for s in all_skills if s.name.startswith(query_clean)), None
            )

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
        self, namespace: str | None = None, query: str | None = None
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

            results.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "namespace": s.namespace or "general",
                    "description": s.description or "",
                }
            )

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
        return [
            {"id": s.id, "name": s.name, "description": s.description or ""}
            for s in skills
        ]

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
                description=self._index_description(s),
            )
            for s in all_skills
        ]
        return self._skills_list_cache

    @staticmethod
    def _index_description(skill: LearnedSkill) -> str:
        """索引条目描述：能力包追加「能力包」标记（capability-packages §6-#7）。

        预挂/加载状态由渲染层按 ctx.metadata.loaded_packages 追加（每轮变化，
        不入缓存）。
        """
        desc = (skill.description or "No description.").replace("\n", " ")
        # G2 瘦身：索引是导航而非全文，SOP 正文承载完整规则。40 条 × 长描述
        # 的 token 开销显著，单条 160 字符足够定位。
        if len(desc) > 160:
            desc = desc[:159].rstrip() + "…"
        if getattr(skill, "capability", None):
            desc = f"{desc} [capability package]"
        return desc


# Singleton
skill_discovery = SkillDiscovery()
