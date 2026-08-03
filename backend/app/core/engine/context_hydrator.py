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

from app.core.context import EvoContext
from app.core.context.cache import LayeredContextCache
from app.core.engine.domain_mapping import resolve_domain
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.message.native_classes import RunnableConfig
from app.core.routing.conversation_state import ConversationState
from app.core.routing.schemas import IntentHint

logger = logging.getLogger(__name__)

# Gating sets for the static layer (active skills / macros / operation map).
# When no intent_hint is available we keep the legacy full-load behavior.
# Intents omitted from a set skip that loader entirely (telescopic loading).
# See docs/supervisor-telescopic-context-design.md §5.4 for the mapping table.
_INTENTS_NEEDING_ACTIVE_SKILLS = frozenset({"worker_task", "ambiguous", "macro_task"})
_INTENTS_NEEDING_ACTIVE_MACROS = frozenset(
    {"macro_task", "builtin_task", "ambiguous", "worker_task"}
)
_INTENTS_NEEDING_OPERATION_MAP = frozenset({"worker_task", "ambiguous"})
_INTENTS_NEEDING_MEMORY = frozenset({"memory_query", "ambiguous"})


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
            intent_hint = intent_hint.model_dump()
        if isinstance(intent_hint, dict):
            domain = intent_hint.get("domain")
            intent = intent_hint.get("intent")
            # L1 emits a domain label and leaves functional resolution to the engine.
            if domain and intent == "domain_classified":
                resolved_intent, resolved_modules = resolve_domain(domain)
                intent = resolved_intent
                intent_hint["intent"] = resolved_intent
                intent_hint["suggested_modules"] = list(resolved_modules)
                # Make the reason explicit about the engine mapping.
                intent_hint["reason"] = (
                    f"{intent_hint.get('reason', '')} -> engine:{resolved_intent}"
                ).strip()

            # §5.9 multi-turn coreference: when the current turn references a prior
            # entity (它/这个/刚才) and the thread has prior context, add "Memory" to
            # suggested_modules so semantic recall is available even for intents
            # (e.g. environment_query) that normally skip it. The routing layer no
            # longer performs this injection; it is part of the engine's mapping.
            has_prior_context = bool(
                intent_hint.get("previous_intent") or intent_hint.get("session_history")
            )
            if has_prior_context:
                temp_hint = IntentHint.model_validate(intent_hint)
                boosted = ConversationState.apply_anaphora_boost(
                    temp_hint, last_human_msg, has_prior_context
                )
                # Persist the boost back into the dict so downstream code sees the
                # resolved intent, modules, and anaphora tag.
                intent_hint.update(boosted.model_dump(exclude_none=True))

            suggested_modules_raw = intent_hint.get("suggested_modules")
            session_history_raw = intent_hint.get("session_history")
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
            from app.constants import DEFAULT_PROJECT_ID

            if ctx.project_id and ctx.project_id != DEFAULT_PROJECT_ID:
                # Project mode: query project + global concepts in parallel, then merge
                project_concepts, global_concepts, episodes = await __import__(
                    "asyncio"
                ).gather(
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
                concepts, episodes = await __import__("asyncio").gather(
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
            from app.core.atlas.source.persistence import operation_map_summary
            from app.core.execution.macro.lifecycle import list_active_macro_index
            from app.core.learning.discovery import skill_discovery

            needs_skills = intent is None or intent in _INTENTS_NEEDING_ACTIVE_SKILLS
            needs_macros = intent is None or intent in _INTENTS_NEEDING_ACTIVE_MACROS
            needs_operation_map = (
                intent is None or intent in _INTENTS_NEEDING_OPERATION_MAP
            ) and ctx.project_id

            async def _load_active_skills() -> Any:
                return (
                    await skill_discovery.get_active_skills_list()
                    if needs_skills
                    else ""
                )

            async def _load_active_macros() -> Any:
                return (
                    await list_active_macro_index(project_id=ctx.project_id)
                    if needs_macros
                    else ""
                )

            async def _load_operation_map() -> Any:
                return (
                    await operation_map_summary(ctx.project_id)
                    if needs_operation_map
                    else ""
                )

            active_skills, active_macros, operation_map = await asyncio.gather(
                _load_active_skills(),
                _load_active_macros(),
                _load_operation_map(),
            )

            data["active_skills"] = active_skills
            data["active_macros"] = active_macros
            data["operation_map"] = operation_map
            return data

        session_id = config.get("configurable", {}).get("run_id", ctx.request_id)
        static_layer = await LayeredContextCache.get_static_layer(
            session_id=session_id,
            project_id=ctx.project_id,
            loader_fn=_load_static_data,
            intent=intent,
        )

        ctx.metadata.project_concepts = static_layer.project_concepts
        ctx.metadata.active_skills = static_layer.active_skills_index
        ctx.metadata.active_macros = static_layer.active_macros_index
        ctx.metadata.operation_map = static_layer.operation_map

        # Memory pipeline — forward cached memory data into context metadata
        ctx.metadata.core_memory_raw = static_layer.hot_memory
        ctx.metadata.episodic_memory_raw = static_layer.episodes

        # 6. Dynamic Layer & Plugins
        # Populate context metadata from flat state fields
        ctx.metadata.shared_context = state.shared_context
        ctx.metadata.tool_memory = state.tool_memory
        ctx.metadata.execution_ticket = state.ticket
        ctx.metadata.iteration_count = iteration_count

        # Backward-compatible duck-typing wrapper for plugins or tools that read ctx.metadata.blackboard
        ctx.metadata.blackboard = state

        from app.core.context.plugins import plugin_registry

        await plugin_registry.ahydrate_context(ctx, intent=intent)

        # 7. Domain Expert Polishing (Event-Driven)
        from app.core.events.publishers import publish_context_polishing

        topic = state.ticket.topic if state.ticket else ""
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
                "[AgentContextHydrator] 🔄 Retry detected: Performing state metadata reset."
            )

            if hasattr(state, "final_outcome"):
                state.final_outcome = None
            if hasattr(state, "shadow_audit"):
                state.shadow_audit = None
            if hasattr(state, "verification"):
                state.verification = None
            if hasattr(state, "route_reason"):
                state.route_reason = None

            # Invalidate static cache for this session to ensure fresh environment scan on retry
            LayeredContextCache.invalidate_static(session_id)
        else:
            if hasattr(state, "final_outcome"):
                state.final_outcome = None
            if hasattr(state, "shadow_audit"):
                state.shadow_audit = None

        duration_ms = (time.time() - start_time) * 1000
        if duration_ms > 100:
            logger.info(
                f"[AgentContextHydrator] Hydration completed in {duration_ms:.1f}ms"
            )
