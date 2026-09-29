"""
EvoContextMiddleware - Unified context hydration with Predictive Memory Loading.

This module implements the context hydration strategy:
1. Predictive Memory Loading: Semantic search results are loaded from Neo4j/Redis.
2. Layered Caching: Static data (skills, telemetry) cached vs Dynamic data fresh.
3. Industrial Hardening: Domain expert polishing, Hot Memory, and Retry logic.
"""

import asyncio
import logging
import time
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context import EvoContext
from app.core.context.cache import LayeredContextCache
from app.core.engine.domain_mapping import resolve_domain
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.message.native_classes import RunnableConfig
from app.core.learning.macro import list_active_macro_index
from app.core.routing.constants import (
    DOMAIN_AMBIGUOUS,
    INTENT_DOMAIN_CLASSIFIED,
    INTENT_MACRO_TASK,
    INTENT_MEMORY_QUERY,
    INTENT_WORKER_TASK,
)
from app.core.routing.conversation_state import ConversationState
from app.core.routing.schemas import IntentHint
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)

# Gating sets for the static layer (active skills / macros / operation map).
# When no intent_hint is available we keep the legacy full-load behavior.
# Intents omitted from a set skip that loader entirely (telescopic loading).
# The per-loader gating sets below are the single source of truth for the
# intent -> loader mapping.
_INTENTS_NEEDING_ACTIVE_SKILLS = frozenset(
    {INTENT_WORKER_TASK, DOMAIN_AMBIGUOUS, INTENT_MACRO_TASK}
)
_INTENTS_NEEDING_ACTIVE_MACROS = frozenset(
    {INTENT_MACRO_TASK, DOMAIN_AMBIGUOUS, INTENT_WORKER_TASK}
)
_INTENTS_NEEDING_MEMORY = frozenset({INTENT_MEMORY_QUERY, DOMAIN_AMBIGUOUS})


async def _resolve_explicit_skills(explicit: list[dict]) -> list:
    """Resolve explicit skill_ids/names into SkillListItem（与全量路径同构）。

    显式 skill_ids（前端勾选 / references 附带）→ 精确预加载，而非全量列表。
    按 id（数字优先）或 name 解析，保证 <available_skills> 只注入用户指定的技能。
    返回 SkillListItem 对象而非 dict：渲染层（prompts._capability_index）按
    getattr(item, "name") 取名，dict 条目会被静默丢弃（2026-09 全链路测试实证）。
    """
    from app.core.learning.schemas import SkillListItem
    from app.core.learning.skills.discovery import skill_discovery

    resolved: list[SkillListItem] = []
    for item in explicit:
        if not isinstance(item, dict):
            continue
        sid = item.get("id") or item.get("skill_id")
        sname = item.get("name") or item.get("skill_name")
        skill = None
        if sid is not None:
            try:
                skill = await skill_discovery.get_skill_by_id(int(sid))
            except (TypeError, ValueError):
                skill = None
        if skill is None and sname:
            match, matched, _ = await skill_discovery.exact_search(str(sname))
            skill = matched[0] if matched else None
        if skill is None:
            continue
        resolved.append(
            SkillListItem(
                id=skill.id,
                name=skill.name,
                namespace=skill.namespace or "general",
                description=(skill.description or "No description.").replace(
                    "\n", " "
                ),
            )
        )
    logger.info(
        "[ContextHydrator] Explicit skills preloaded: %s",
        [r.name for r in resolved],
    )
    return resolved


class AgentContextHydrator:
    """
    Unified context hydration service.
    Handles hydration of Environment, Project, and Memory ONCE per session.
    """

    @classmethod
    async def _get_shared_memory_container(cls) -> Any:
        """Get shared MemoryContainer via MemoryLifespanManager (singleton)."""
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()

        return MemoryLifespanManager.get_container()

    @staticmethod
    async def hydrate(
        ctx: EvoContext,
        state: Any,
        config: RunnableConfig,
        last_human_msg: str = "",
        is_retry: bool = False,
        iteration_count: int = 0,
    ) -> None:
        """
        Layered context hydration with caching and predictive memory loading.
        Mutates ctx.metadata and state directly.
        """
        start_time = time.time()

        # 1. Trigger SessionStart Hook
        session_start_result = await hook_system.trigger(
            HookEvent.SESSION_START,
            HookContext(
                thread_id=ctx.thread_id,
                project_id=ctx.project_id,
                member_id=ctx.member_id,
                state=state,
            ),
        )
        if (
            session_start_result.modified_context
            and session_start_result.modified_context.state
        ):
            mod_state = session_start_result.modified_context.state
            if isinstance(mod_state, dict):
                for k, v in mod_state.items():
                    setattr(state, k, v)
            elif hasattr(mod_state, "model_fields_set"):
                for k in mod_state.model_fields_set:
                    setattr(state, k, getattr(mod_state, k))

        # Resolve intent early so Tier 2 memory loading can be gated.
        intent_hint = ctx.metadata.get("intent_hint") or config.get("metadata", {}).get(
            "intent_hint"
        )
        if isinstance(intent_hint, IntentHint):
            intent_hint_obj = intent_hint
        elif isinstance(intent_hint, dict):
            intent_hint_obj = IntentHint.model_validate(intent_hint)
        else:
            intent_hint_obj = None

        if intent_hint_obj is not None:
            domain = intent_hint_obj.domain
            intent = intent_hint_obj.intent
            # L1/host emits a domain label; functional resolution is profile-first
            # （项目侧 capability profile 声明 intent/modules）→ domain_mapping 默认。
            if domain and intent == INTENT_DOMAIN_CLASSIFIED:
                from app.core.engine.capability_profiles import get_profile

                _profile = get_profile(domain, ctx.working_directory)
                _default_intent, _default_modules = resolve_domain(domain)
                resolved_intent = (
                    _profile.intent
                    if _profile is not None and _profile.intent
                    else _default_intent
                )
                resolved_modules = (
                    _profile.modules
                    if _profile is not None and _profile.modules
                    else list(_default_modules)
                )
                intent = resolved_intent
                intent_hint_obj = intent_hint_obj.model_copy(
                    update={
                        "intent": resolved_intent,
                        "suggested_modules": list(resolved_modules),
                        "reason": f"{intent_hint_obj.reason} -> engine:{resolved_intent}",
                    }
                )

            # §5.9 multi-turn coreference: when the current turn references a prior
            # entity (它/这个/刚才) and the thread has prior context, add "Memory" to
            # suggested_modules so semantic recall is available even for intents
            # (e.g. environment_query) that normally skip it. The routing layer no
            # longer performs this injection; it is part of the engine's mapping.
            has_prior_context = bool(
                intent_hint_obj.previous_intent or intent_hint_obj.session_history
            )
            if has_prior_context:
                boosted = ConversationState.apply_anaphora_boost(
                    intent_hint_obj, last_human_msg, has_prior_context
                )
                intent_hint_obj = intent_hint_obj.model_copy(
                    update=boosted.model_dump(exclude_none=True)
                )

            # 写回 resolved hint：下游能力装配（ToolsManager 域过滤等）从 ctx 读，
            # 不应再各自解析 config.metadata 的原始 hint
            ctx.metadata.intent_hint = intent_hint_obj

            suggested_modules_raw = intent_hint_obj.suggested_modules
            session_history_raw = intent_hint_obj.session_history
        else:
            intent = None
            suggested_modules_raw = None
            session_history_raw = None

        suggested_modules: set[str] = (
            set(suggested_modules_raw)
            if isinstance(suggested_modules_raw, list)
            else set()
        )
        # When the anaphora path is active, blend the running session history into
        # the memory query so semantic recall can surface entities named in
        # earlier turns (e.g. "Apple M1 Max") that are absent from the bare
        # anaphora turn ("那它的内存呢"). Prior turns are weighted first so the
        # recency bias matches how LLMs resolve references.
        anaphora_active = (
            "Memory" in suggested_modules and intent not in _INTENTS_NEEDING_MEMORY
        )
        if (
            anaphora_active
            and isinstance(session_history_raw, list)
            and session_history_raw
        ):
            memory_query_text = " ".join(session_history_raw[-3:] + [last_human_msg])
        else:
            memory_query_text = last_human_msg

        memory_data = {}
        memory_container = await AgentContextHydrator._get_shared_memory_container()
        memory_manager = memory_container.memory_manager

        # Tier 1: Hot Memory (High Priority Instructions)
        hot_memory = await memory_manager.get_hot_memory(ctx.project_id)
        if hot_memory:
            memory_data["hot_memory"] = hot_memory

        # Tier 2: Predictive load (Concepts & Episodes - Only for primary turns)
        # Gated by intent: only memory_query and ambiguous need semantic recall.
        # An intents's suggested_modules containing "Memory" (anaphora path)
        # soft-opens this gate so cross-turn entity recall stays available.
        # When intent is None (no L0 hint available), keep legacy full-load behavior.
        if last_human_msg and (
            intent is None
            or intent in _INTENTS_NEEDING_MEMORY
            or "Memory" in suggested_modules
        ):
            if ctx.project_id and ctx.project_id != DEFAULT_PROJECT_ID:
                # Project mode: query project + global concepts in parallel, then merge
                project_concepts, global_concepts, episodes = await asyncio.gather(
                    memory_manager.search_concepts(
                        memory_query_text, ctx.project_id, limit=3
                    ),
                    memory_manager.search_concepts(
                        memory_query_text, DEFAULT_PROJECT_ID, limit=2
                    ),
                    memory_manager.search_episodes(
                        memory_query_text, ctx.project_id, limit=3
                    ),
                )
                # Merge: project concepts first, then global (dedup by name)
                seen_names: set[str] = set()
                merged_concepts: list = []
                for c in list(project_concepts) + list(global_concepts):
                    if c.name not in seen_names:
                        seen_names.add(c.name)
                        merged_concepts.append(c)
                concepts = merged_concepts[:5]
            else:
                # Global mode: query global only
                concepts, episodes = await asyncio.gather(
                    memory_manager.search_concepts(memory_query_text, ctx.project_id),
                    memory_manager.search_episodes(
                        memory_query_text, ctx.project_id, limit=3
                    ),
                )

            if concepts:
                current_thread_id = ctx.thread_id
                sorted_concepts = sorted(
                    concepts,
                    key=lambda c: (c.source_thread_id != current_thread_id,),
                )
                memory_data["project_concepts"] = "\n".join(
                    [f"- **{c.name}**: {c.description}" for c in sorted_concepts[:5]]
                )
            if episodes:
                current_run_id = config.get("configurable", {}).get("run_id")
                filtered = [
                    e for e in episodes if e.get("id") != f"ep_{current_run_id}"
                ]
                if filtered:
                    memory_data["episodes"] = "\n".join(
                        [
                            f"- **Goal**: {e['goal']}\n  **Result**: {e['result']}"
                            for e in filtered[:2]
                        ]
                    )

        # 5. Static Layer (Skills, Telemetry)
        # intent already resolved above for gating Tier 2 memory.

        async def _load_static_data() -> dict[str, Any]:
            data = dict(memory_data)
            from app.core.learning.skills.discovery import skill_discovery

            needs_skills = intent is None or intent in _INTENTS_NEEDING_ACTIVE_SKILLS
            needs_macros = intent is None or intent in _INTENTS_NEEDING_ACTIVE_MACROS

            async def _load_active_skills() -> Any:
                # 显式技能（前端勾选 / references 附带）优先于 intent 门控：
                # 用户显式指定的技能必须可见，分类器意图不得静默丢弃用户选择
                # （原实现 explicit 检查在 needs_skills 判假之后，勾选被裁——
                # 2026-09 全链路测试 test_explicit_skills_bypass_intent_gate 实证）。
                explicit = (config.get("metadata") or {}).get("explicit_skills")
                if explicit:
                    return await _resolve_explicit_skills(explicit)
                if not needs_skills:
                    return ""
                return await skill_discovery.get_active_skills_list()

            async def _load_active_macros() -> Any:
                return (
                    await list_active_macro_index(project_id=ctx.project_id)
                    if needs_macros
                    else ""
                )

            active_skills, active_macros = await asyncio.gather(
                _load_active_skills(),
                _load_active_macros(),
            )

            data["active_skills"] = active_skills
            data["active_macros"] = active_macros
            return data

        # 审计修复：键原用 run_id（每轮 delivery 重新生成）→ 静态层永不命中
        # 且条目只增不减（进程级泄漏）。改 thread 级稳定键。
        session_id = ctx.thread_id or config.get("configurable", {}).get(
            "run_id", ctx.request_id
        )
        explicit = (config.get("metadata") or {}).get("explicit_skills") or []
        explicit_key = "|".join(
            sorted(
                str(x.get("id") or x.get("skill_id") or x.get("name") or "")
                for x in explicit
                if isinstance(x, dict)
            )
        )
        # 页面级包预选（v3）——必须在缓存加载器之外每轮执行（预选是写 ctx
        # 的副作用，依赖「每轮确定性重算」；埋进 loader 会随缓存命中被跳过）。
        # 域→包目录走 DB（包自声明 capability.domain），页面预挂 =
        # host_ctx.route 经包 route_patterns 匹配 + 预挂包 server
        # ensure_connected（G4：写工具经 confirm_tools 排除，须显式加载包）。
        try:
            from app.core.engine.preselection import (
                preload_preselection,
                resolve_preselection,
            )

            hint = ctx.metadata.intent_hint
            domain = None
            if hint is not None:
                domain = getattr(hint, "domain", None) or (
                    hint.get("domain") if isinstance(hint, dict) else None
                )
            preselected = await resolve_preselection(
                domain,
                (config.get("metadata") or {}).get("host_context"),
            )
            await preload_preselection(preselected, ctx)
        except Exception:
            logger.exception("[Hydrator] package preselection failed (ignored)")

        static_layer = await LayeredContextCache.get_static_layer(
            session_id=session_id,
            project_id=ctx.project_id,
            loader_fn=_load_static_data,
            intent=intent,
            explicit_key=explicit_key,
        )

        ctx.metadata.project_concepts = static_layer.project_concepts
        ctx.metadata.active_skills = static_layer.active_skills_index
        ctx.metadata.active_macros = static_layer.active_macros_index

        # Memory pipeline — forward cached memory data into context metadata
        if settings.ENABLE_MEMORY:
            ctx.metadata.core_memory_raw = static_layer.hot_memory
            ctx.metadata.episodic_memory_raw = static_layer.episodes

        # 6. Dynamic Layer & Plugins
        # Populate context metadata from flat state fields
        ctx.metadata.shared_context = state.shared_context
        ctx.metadata.tool_memory = state.tool_memory
        ctx.metadata.iteration_count = iteration_count

        # 冗余清理：不再把整个 state 挂进 metadata（唯一消费者 memory
        # 工具已改读 shared_context）。置 None 以清洗旧 thread 残留的
        # 全量 state 副本（否则 save 全量 model_dump 会把残留反复写回）。
        ctx.metadata.blackboard = None

        from app.core.context.plugins import plugin_registry

        await plugin_registry.ahydrate_context(ctx, intent=intent)

        # 7. Domain Expert Polishing (Event-Driven)
        from app.core.events.publishers import publish_context_polishing

        topic = state.session_goal or ""
        await publish_context_polishing(
            thread_id=ctx.thread_id,
            project_id=ctx.project_id,
            model=ctx.active_model,
            context={
                "ctx": ctx,
                "topic": topic,
            },
        )

        # 8. Retry Hardening (Metadata Reset)
        is_config_retry = config.get("metadata", {}).get("is_retry", False)
        if (is_retry or is_config_retry) and iteration_count == 0:
            logger.info(
                "[AgentContextHydrator] 🔄 Retry detected: invalidating static cache."
            )
            # Invalidate static cache for this session to ensure fresh environment scan on retry
            LayeredContextCache.invalidate_static(session_id)

        duration_ms = elapsed_ms(start_time)
        if duration_ms > 100:
            logger.info(
                f"[AgentContextHydrator] Hydration completed in {duration_ms:.1f}ms"
            )
